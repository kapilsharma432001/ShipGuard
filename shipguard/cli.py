from pathlib import Path

import typer

from shipguard.context_builder import (
    format_memory_for_prompt,
    format_memory_summary,
    load_or_build_project_context,
    update_memory_after_analysis,
)
from shipguard.git_analyzer import (
    GitAnalyzerError,
    collect_git_changes,
    format_release_prompt,
)
from shipguard.github_client import (
    GitHubClient,
    GitHubClientError,
    format_pr_prompt,
)
from shipguard.llm_client import (
    LLMClient,
    ShipGuardConfigError,
    ShipGuardLLMError,
)
from shipguard.models import ReleaseRiskReport
from shipguard.project_memory import ProjectMemoryError, ProjectMemoryStore
from shipguard.pr_url_parser import InvalidPRURLError, parse_github_pr_url

app = typer.Typer(
    help="AI Release Risk Reasoner.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """ShipGuard command group."""


@app.command()
def analyze(
    repo: Path = typer.Option(
        ...,
        "--repo",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Path to the repository to analyze.",
    ),
    max_diff_chars: int = typer.Option(
        30_000,
        "--max-diff-chars",
        min=1,
        help="Maximum git diff characters to send to the LLM.",
    ),
) -> None:
    """Analyze release risk for a repository."""
    if not repo.exists():
        typer.secho(
            f"Repository path does not exist: {repo}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    typer.echo(f"Analyzing repository: {repo}")

    try:
        git_summary = collect_git_changes(repo, max_diff_chars=max_diff_chars)
        client = LLMClient.from_env()
        report = client.analyze_release(format_release_prompt(git_summary))
    except GitAnalyzerError as exc:
        typer.secho(f"Git error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    except ShipGuardConfigError as exc:
        typer.secho(f"Configuration error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    except ShipGuardLLMError as exc:
        typer.secho(f"LLM error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    _print_report(report)


@app.command("analyze-pr")
def analyze_pr(
    pr_url: str = typer.Option(
        ...,
        "--pr-url",
        help="GitHub pull request URL to analyze.",
    ),
    max_diff_chars: int = typer.Option(
        120_000,
        "--max-diff-chars",
        min=1,
        help="Maximum PR diff characters to send to the LLM.",
    ),
    use_memory: bool = typer.Option(
        True,
        "--use-memory/--no-memory",
        help="Include repository-level ShipGuard memory in PR analysis.",
    ),
    rebuild_memory: bool = typer.Option(
        False,
        "--rebuild-memory",
        help="Rebuild repository memory from the PR base SHA.",
    ),
    memory_dir: Path = typer.Option(
        Path(".shipguard/memory"),
        "--memory-dir",
        file_okay=False,
        dir_okay=True,
        help="Directory for local ShipGuard memory files.",
    ),
    show_memory_summary: bool = typer.Option(
        False,
        "--show-memory-summary",
        help="Print a brief memory summary before the risk report.",
    ),
) -> None:
    """Analyze release risk for a GitHub pull request."""
    try:
        pr_ref = parse_github_pr_url(pr_url)
    except InvalidPRURLError as exc:
        typer.secho(f"Invalid PR URL: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Analyzing pull request: {pr_ref.url}")

    try:
        github_client = GitHubClient.from_env()
        pr_summary = github_client.fetch_pr_changes(
            pr_ref,
            max_diff_chars=max_diff_chars,
        )
        llm_client: LLMClient | None = None
        llm_config_error: ShipGuardConfigError | None = None
        try:
            llm_client = LLMClient.from_env()
        except ShipGuardConfigError as exc:
            llm_config_error = exc

        memory_context: str | None = None
        memory_store: ProjectMemoryStore | None = None
        memory_package = None
        if use_memory:
            memory_store = ProjectMemoryStore(
                memory_dir=memory_dir,
                owner=pr_summary.owner,
                repo=pr_summary.repo,
            )
            memory_package = load_or_build_project_context(
                github_client=github_client,
                pr_summary=pr_summary,
                store=memory_store,
                llm_client=llm_client,
                rebuild=rebuild_memory,
            )
            memory_context = format_memory_for_prompt(
                memory_package.memory,
                memory_package.file_contexts,
                memory_package.release_history,
            )
            if show_memory_summary:
                typer.echo()
                typer.echo(format_memory_summary(memory_package, memory_store))
        elif show_memory_summary:
            typer.echo()
            typer.echo("Project Memory Summary: disabled for this run.")

        if llm_config_error is not None or llm_client is None:
            raise llm_config_error or ShipGuardConfigError("missing LLM configuration.")

        report = llm_client.analyze_release(format_pr_prompt(pr_summary, memory_context))
        if use_memory and memory_store is not None and memory_package is not None:
            update_memory_after_analysis(
                store=memory_store,
                memory=memory_package.memory,
                pr_summary=pr_summary,
                report=report,
            )
    except GitHubClientError as exc:
        typer.secho(f"GitHub error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except ProjectMemoryError as exc:
        typer.secho(f"Project memory error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except ShipGuardConfigError as exc:
        typer.secho(f"Configuration error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    except ShipGuardLLMError as exc:
        typer.secho(f"LLM error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    _print_report(report)


def _print_report(report: ReleaseRiskReport) -> None:
    typer.echo()
    typer.echo(f"Release Readiness Score: {report.release_readiness_score}")
    typer.echo(f"Decision: {report.decision}")
    typer.echo(f"Risk Level: {report.risk_level}")
    typer.echo("What may break:")
    for item in report.what_may_break:
        typer.echo(f"- {item}")
    typer.echo("What CI may miss:")
    for item in report.what_ci_may_miss:
        typer.echo(f"- {item}")
