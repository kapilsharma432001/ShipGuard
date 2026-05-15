from pathlib import Path

import typer

from shipguard.llm_client import (
    LLMClient,
    ShipGuardConfigError,
    ShipGuardLLMError,
)

app = typer.Typer(
    help="AI Release Risk Reasoner.",
    no_args_is_help=True,
)


TEST_RELEASE_PROMPT = (
    "Analyze this fake release: API enum changed from Denied to DENIED. "
    "DB migration adds NOT NULL column without default. What can break?"
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
        client = LLMClient.from_env()
        report = client.analyze_release(TEST_RELEASE_PROMPT)
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
