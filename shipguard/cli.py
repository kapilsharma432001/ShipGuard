from pathlib import Path

import typer

from shipguard.git_analyzer import (
    GitAnalyzerError,
    collect_git_changes,
    format_release_prompt,
)
from shipguard.llm_client import (
    LLMClient,
    ShipGuardConfigError,
    ShipGuardLLMError,
)

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
