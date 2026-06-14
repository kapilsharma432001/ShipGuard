from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from shipguard.context_builder import ProjectContextPackage, classify_file
from shipguard.models import PRChangeSummary, ReleaseRiskReport
from shipguard.project_memory import ProjectMemoryStore


REPORTS_DIR = Path(".shipguard/reports")


class ReportGenerationError(RuntimeError):
    """Raised when ShipGuard cannot write release passport artifacts."""


class ReportArtifacts(BaseModel):
    markdown_path: str
    analysis_json_path: str
    html_path: str | None = None


def generate_release_passport(
    pr_summary: PRChangeSummary,
    report: ReleaseRiskReport,
    memory_package: ProjectContextPackage | None = None,
    memory_store: ProjectMemoryStore | None = None,
    include_html: bool = False,
    output_root: Path = REPORTS_DIR,
) -> ReportArtifacts:
    output_dir = output_root / _report_dir_name(pr_summary)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ReportGenerationError(f"could not create report directory: {output_dir}") from exc

    markdown_path = output_dir / "release_passport.md"
    html_path = output_dir / "release_passport.html" if include_html else None
    analysis_json_path = output_dir / "analysis.json"
    artifacts = ReportArtifacts(
        markdown_path=str(markdown_path),
        html_path=str(html_path) if html_path else None,
        analysis_json_path=str(analysis_json_path),
    )
    analysis = _build_analysis_object(
        pr_summary=pr_summary,
        report=report,
        memory_package=memory_package,
        memory_store=memory_store,
        generated_at=_now_utc_iso(),
        artifacts=artifacts,
    )

    try:
        markdown_path.write_text(_render_markdown(analysis), encoding="utf-8")
        if html_path is not None:
            html_path.write_text(_render_html(analysis), encoding="utf-8")
        analysis_json_path.write_text(
            json.dumps(analysis, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise ReportGenerationError(f"could not write report artifacts: {output_dir}") from exc
    return artifacts


def _build_analysis_object(
    pr_summary: PRChangeSummary,
    report: ReleaseRiskReport,
    memory_package: ProjectContextPackage | None,
    memory_store: ProjectMemoryStore | None,
    generated_at: str,
    artifacts: ReportArtifacts,
) -> dict[str, Any]:
    changed_files = _changed_file_rows(pr_summary)
    memory_summary = _memory_summary(memory_package, memory_store)
    missing_evidence = _missing_evidence(pr_summary, memory_package)
    return {
        "title": "ShipGuard Release Passport",
        "tagline": (
            "CI tells you whether tests passed. ShipGuard helps identify "
            "whether the release looks risky."
        ),
        "generated_at": generated_at,
        "repository": f"{pr_summary.owner}/{pr_summary.repo}",
        "pr": pr_summary.model_dump(mode="json"),
        "release_risk_report": report.model_dump(mode="json"),
        "executive_summary": _executive_summary(report, pr_summary),
        "project_memory_summary": memory_summary,
        "changed_files": changed_files,
        "missing_evidence": missing_evidence,
        "safer_rollout_plan": _safer_rollout_plan(report, pr_summary, missing_evidence),
        "rollback_plan": _rollback_plan(report, changed_files),
        "score_breakdown": _score_breakdown(report, missing_evidence),
        "appendix": _appendix(pr_summary, memory_summary),
        "generated_artifact_paths": artifacts.model_dump(mode="json"),
    }


def _render_markdown(analysis: dict[str, Any]) -> str:
    pr = analysis["pr"]
    risk_report = analysis["release_risk_report"]
    memory = analysis["project_memory_summary"]
    artifacts = analysis["generated_artifact_paths"]
    changed_files = analysis["changed_files"]
    appendix = analysis["appendix"]

    lines = [
        "# ShipGuard Release Passport",
        "",
        analysis["tagline"],
        "",
        "## Repository and PR details",
        "",
        f"- Repository: {analysis['repository']}",
        f"- PR: #{pr['pr_number']} - {pr['title']}",
        f"- PR URL: {pr['pr_url']}",
        f"- State: {pr['state']}",
        f"- Base branch: {pr['base_branch']} ({pr['base_sha']})",
        f"- Head branch: {pr['head_branch']} ({pr['head_sha']})",
        f"- Additions: {pr['additions']}",
        f"- Deletions: {pr['deletions']}",
        f"- Changed files: {pr['changed_files_count']}",
        "",
        "## Generated timestamp",
        "",
        analysis["generated_at"],
        "",
        "## Release Readiness Score",
        "",
        str(risk_report["release_readiness_score"]),
        "",
        "## Decision",
        "",
        risk_report["decision"],
        "",
        "## Risk Level",
        "",
        risk_report["risk_level"],
        "",
        "## Executive summary",
        "",
        analysis["executive_summary"],
        "",
        "## Project Memory Summary",
        "",
        _markdown_memory(memory),
        "",
        "## Changed files",
        "",
        "| File | Category | Diff evidence |",
        "| --- | --- | --- |",
    ]
    lines.extend(
        f"| `{row['path']}` | {row['category']} | {row['diff_evidence']} |"
        for row in changed_files
    )
    lines.extend(
        [
            "",
            "## What may break",
            "",
            *_markdown_list(risk_report["what_may_break"]),
            "",
            "## What CI may miss",
            "",
            *_markdown_list(risk_report["what_ci_may_miss"]),
            "",
            "## Missing evidence",
            "",
            *_markdown_list(analysis["missing_evidence"]),
            "",
            "## Safer rollout plan",
            "",
            *_markdown_list(analysis["safer_rollout_plan"]),
            "",
            "## Rollback plan",
            "",
            *_markdown_list(analysis["rollback_plan"]),
            "",
            "## Score breakdown if available",
            "",
            *_markdown_list(analysis["score_breakdown"]),
            "",
            "## Appendix: memory and diff context summary",
            "",
            *_markdown_list(appendix),
            "",
            "## Generated artifacts",
            "",
            f"- Markdown: `{artifacts['markdown_path']}`",
            f"- HTML: `{artifacts['html_path'] or 'not generated'}`",
            f"- JSON: `{artifacts['analysis_json_path']}`",
            "",
        ]
    )
    return "\n".join(lines)


def _render_html(analysis: dict[str, Any]) -> str:
    pr = analysis["pr"]
    risk_report = analysis["release_risk_report"]
    memory = analysis["project_memory_summary"]
    changed_files = analysis["changed_files"]
    artifacts = analysis["generated_artifact_paths"]
    decision_class = _badge_class(risk_report["decision"])
    risk_class = _badge_class(risk_report["risk_level"])
    score = int(risk_report["release_readiness_score"])
    score_color = _score_color(score)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ShipGuard Release Passport - PR #{escape(str(pr['pr_number']))}</title>
  <style>
    :root {{
      --ink: #111827;
      --muted: #667085;
      --line: #d7dde8;
      --panel: #ffffff;
      --page: #f5f7fb;
      --teal: #0f766e;
      --blue: #2563eb;
      --amber: #b45309;
      --red: #b91c1c;
      --green: #15803d;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--page);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }}
    .hero {{
      color: #fff;
      padding: 56px 28px 36px;
      background:
        linear-gradient(135deg, #111827 0%, #1f2937 45%, #0f766e 100%);
      border-bottom: 6px solid #f59e0b;
    }}
    .wrap {{ max-width: 1180px; margin: 0 auto; }}
    .eyebrow {{
      color: #a7f3d0;
      font-size: 13px;
      font-weight: 800;
      letter-spacing: 0;
      text-transform: uppercase;
    }}
    h1 {{
      margin: 12px 0 10px;
      font-size: clamp(38px, 7vw, 78px);
      line-height: .95;
      letter-spacing: 0;
    }}
    .tagline {{
      max-width: 780px;
      margin: 0;
      color: #dbeafe;
      font-size: 20px;
    }}
    .hero-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 260px;
      gap: 24px;
      align-items: end;
    }}
    .score-card {{
      background: rgba(255,255,255,.12);
      border: 1px solid rgba(255,255,255,.26);
      border-radius: 8px;
      padding: 22px;
      backdrop-filter: blur(8px);
    }}
    .score {{
      font-size: 74px;
      line-height: .9;
      font-weight: 900;
      color: {score_color};
    }}
    .score-label {{ color: #e5e7eb; font-weight: 700; margin-top: 8px; }}
    main {{ padding: 28px; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 18px;
      margin-bottom: 18px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 20px;
      box-shadow: 0 14px 36px rgba(15, 23, 42, .07);
    }}
    .span-12 {{ grid-column: span 12; }}
    .span-8 {{ grid-column: span 8; }}
    .span-6 {{ grid-column: span 6; }}
    .span-4 {{ grid-column: span 4; }}
    .span-3 {{ grid-column: span 3; }}
    h2 {{ margin: 0 0 14px; font-size: 22px; letter-spacing: 0; }}
    h3 {{ margin: 0 0 8px; font-size: 15px; color: var(--muted); letter-spacing: 0; text-transform: uppercase; }}
    p {{ margin: 0 0 12px; }}
    .badges {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 20px; }}
    .badge {{
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 6px 11px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 900;
      border: 1px solid transparent;
    }}
    .badge.allow, .badge.low {{ color: #065f46; background: #dcfce7; border-color: #86efac; }}
    .badge.review, .badge.medium {{ color: #92400e; background: #fef3c7; border-color: #fcd34d; }}
    .badge.block, .badge.high, .badge.critical {{ color: #991b1b; background: #fee2e2; border-color: #fca5a5; }}
    .metric {{
      font-size: 34px;
      font-weight: 900;
      line-height: 1;
    }}
    .metric-label {{ color: var(--muted); font-size: 13px; margin-top: 6px; }}
    .risk-list {{ display: grid; gap: 12px; }}
    .risk-item {{
      border-left: 4px solid var(--red);
      background: #fff7f7;
      border-radius: 8px;
      padding: 14px;
    }}
    .checklist {{ display: grid; gap: 10px; padding: 0; margin: 0; list-style: none; }}
    .checklist li {{
      padding: 12px 12px 12px 38px;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      position: relative;
    }}
    .checklist li:before {{
      content: "";
      position: absolute;
      left: 14px;
      top: 16px;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--blue);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      overflow: hidden;
      border-radius: 8px;
      border: 1px solid var(--line);
    }}
    th, td {{
      padding: 11px 12px;
      text-align: left;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
      font-size: 14px;
    }}
    th {{ background: #eef2ff; color: #3730a3; font-size: 12px; text-transform: uppercase; }}
    tr:last-child td {{ border-bottom: 0; }}
    code {{
      color: #0f172a;
      background: #eef2f7;
      border: 1px solid #d8e0ec;
      border-radius: 6px;
      padding: 2px 5px;
      word-break: break-word;
    }}
    .two-col {{ columns: 2; column-gap: 24px; }}
    .two-col li {{ break-inside: avoid; margin-bottom: 8px; }}
    .muted {{ color: var(--muted); }}
    footer {{
      padding: 24px 28px 42px;
      color: var(--muted);
      text-align: center;
    }}
    @media (max-width: 860px) {{
      .hero-grid, .grid {{ display: block; }}
      .card, .score-card {{ margin-bottom: 16px; }}
      .two-col {{ columns: 1; }}
      h1 {{ font-size: 42px; }}
    }}
  </style>
</head>
<body>
  <section class="hero">
    <div class="wrap hero-grid">
      <div>
        <div class="eyebrow">ShipGuard Release Passport</div>
        <h1>{escape(analysis['repository'])}<br>PR #{escape(str(pr['pr_number']))}</h1>
        <p class="tagline">{escape(analysis['tagline'])}</p>
        <div class="badges">
          <span class="badge {decision_class}">Decision: {escape(risk_report['decision'])}</span>
          <span class="badge {risk_class}">Risk: {escape(risk_report['risk_level'])}</span>
        </div>
      </div>
      <div class="score-card">
        <div class="score">{score}</div>
        <div class="score-label">Release Readiness Score</div>
      </div>
    </div>
  </section>
  <main>
    <div class="wrap">
      <section class="grid">
        {_metric_card('Changed files', pr['changed_files_count'])}
        {_metric_card('Additions', pr['additions'])}
        {_metric_card('Deletions', pr['deletions'])}
        {_metric_card('Indexed files', memory['indexed_files'])}
      </section>
      <section class="grid">
        <div class="card span-8">
          <h2>Executive Summary</h2>
          <p>{escape(analysis['executive_summary'])}</p>
          <p class="muted">PR: <a href="{escape(pr['pr_url'])}">{escape(pr['title'])}</a></p>
        </div>
        <div class="card span-4">
          <h2>Project Memory</h2>
          {_memory_html(memory)}
        </div>
      </section>
      <section class="grid">
        <div class="card span-6">
          <h2>What May Break</h2>
          <div class="risk-list">{_risk_cards(risk_report['what_may_break'])}</div>
        </div>
        <div class="card span-6">
          <h2>What CI May Miss</h2>
          <ul class="checklist">{_li_items(risk_report['what_ci_may_miss'])}</ul>
        </div>
      </section>
      <section class="grid">
        <div class="card span-12">
          <h2>Changed Files</h2>
          {_changed_files_table(changed_files)}
        </div>
      </section>
      <section class="grid">
        <div class="card span-4">
          <h2>Missing Evidence</h2>
          <ul class="checklist">{_li_items(analysis['missing_evidence'])}</ul>
        </div>
        <div class="card span-4">
          <h2>Safer Rollout Plan</h2>
          <ul class="checklist">{_li_items(analysis['safer_rollout_plan'])}</ul>
        </div>
        <div class="card span-4">
          <h2>Rollback Plan</h2>
          <ul class="checklist">{_li_items(analysis['rollback_plan'])}</ul>
        </div>
      </section>
      <section class="grid">
        <div class="card span-6">
          <h2>Score Breakdown</h2>
          <ul class="checklist">{_li_items(analysis['score_breakdown'])}</ul>
        </div>
        <div class="card span-6">
          <h2>Appendix</h2>
          <ul class="checklist">{_li_items(analysis['appendix'])}</ul>
        </div>
      </section>
      <section class="grid">
        <div class="card span-12">
          <h2>Generated Artifacts</h2>
          <p><code>{escape(artifacts['markdown_path'])}</code></p>
          <p><code>{escape(artifacts['html_path'] or 'HTML not generated')}</code></p>
          <p><code>{escape(artifacts['analysis_json_path'])}</code></p>
        </div>
      </section>
    </div>
  </main>
  <footer>Generated by ShipGuard at {escape(analysis['generated_at'])}</footer>
</body>
</html>
"""


def _changed_file_rows(pr_summary: PRChangeSummary) -> list[dict[str, str]]:
    included = set(pr_summary.included_files)
    partial = set(pr_summary.partially_included_files)
    omitted = set(pr_summary.omitted_files)
    rows: list[dict[str, str]] = []
    for path in pr_summary.changed_files:
        if path in included:
            evidence = "Included"
        elif path in partial:
            evidence = "Partially included"
        elif path in omitted:
            evidence = "Omitted"
        else:
            evidence = "No text diff section"
        rows.append(
            {
                "path": path,
                "category": classify_file(path),
                "extension": Path(path).suffix.lower() or "none",
                "diff_evidence": evidence,
            }
        )
    return rows


def _memory_summary(
    package: ProjectContextPackage | None,
    store: ProjectMemoryStore | None,
) -> dict[str, Any]:
    if package is None:
        return {
            "used": False,
            "memory_directory": str(store.path) if store else None,
            "rebuilt": False,
            "summary_source": "NOT_USED",
            "total_files_discovered": 0,
            "files_content_fetched": 0,
            "files_skipped": 0,
            "tree_truncated": False,
            "tree_truncation_warning": None,
            "indexed_files": 0,
            "known_categories_count": {},
            "architecture_summary": None,
            "known_release_risks": [],
        }
    report = package.build_report
    return {
        "used": True,
        "memory_directory": str(store.path) if store else None,
        "rebuilt": package.rebuilt,
        "summary_source": package.memory.summary_source,
        "total_files_discovered": report.total_files_discovered,
        "files_content_fetched": report.files_content_fetched,
        "files_skipped": report.files_skipped,
        "tree_truncated": report.tree_truncated,
        "tree_truncation_warning": report.tree_truncation_warning,
        "indexed_files": len(package.file_contexts),
        "inventory_files": len(package.inventory),
        "known_categories_count": _category_counts(package.inventory),
        "architecture_summary": package.memory.architecture_summary,
        "known_release_risks": package.memory.known_release_risks[:12],
        "known_env_vars_count": len(package.memory.known_env_vars),
        "known_db_tables_count": len(package.memory.known_db_tables),
        "last_indexed_base_sha": package.memory.last_indexed_base_sha,
        "last_analyzed_head_sha": package.memory.last_analyzed_head_sha,
    }


def _missing_evidence(
    pr_summary: PRChangeSummary,
    package: ProjectContextPackage | None,
) -> list[str]:
    evidence: list[str] = []
    if pr_summary.partially_included_files:
        evidence.append(
            "Some changed file diffs were only partially included: "
            + ", ".join(pr_summary.partially_included_files[:12])
        )
    if pr_summary.omitted_files:
        evidence.append(
            "Some changed file diffs were omitted due to context budget: "
            + ", ".join(pr_summary.omitted_files[:12])
        )
    if not pr_summary.body:
        evidence.append("The PR has no description body explaining rollout or rollback intent.")
    if package is None:
        evidence.append("Project memory was not used, so repository context is limited to the PR diff.")
    elif package.build_report.tree_truncated:
        evidence.append(
            "GitHub reported a truncated repository tree while building memory: "
            + (package.build_report.tree_truncation_warning or "no warning details")
        )
    if not evidence:
        evidence.append("No major missing evidence was detected from the available PR diff and memory context.")
    return evidence


def _safer_rollout_plan(
    report: ReleaseRiskReport,
    pr_summary: PRChangeSummary,
    missing_evidence: list[str],
) -> list[str]:
    plan = [
        "Run the full CI suite and targeted regression tests for the changed API, data, config, and deployment surfaces.",
        "Deploy to a staging or canary environment first and compare error rate, latency, and key business metrics before widening exposure.",
    ]
    if report.decision.value == "BLOCK_RELEASE":
        plan.insert(0, "Do not merge or deploy until the blocking release risks have explicit fixes and reviewer sign-off.")
    elif report.decision.value == "REVIEW_REQUIRED":
        plan.insert(0, "Require focused human review on the highest-risk files before merge or deployment.")
    else:
        plan.insert(0, "Proceed through the normal release path with standard verification and monitoring.")
    if _has_category(pr_summary.changed_files, {"MIGRATION", "DB_MODEL"}):
        plan.append("Validate database migrations against production-like data, including backfill, lock duration, and backward compatibility.")
    if _has_category(pr_summary.changed_files, {"CONFIG", "DEPLOYMENT", "CI_CD"}):
        plan.append("Confirm environment variables, deployment manifests, and runtime settings are present in every target environment.")
    if _has_category(pr_summary.changed_files, {"API"}):
        plan.append("Notify API consumers or gate the change when request/response shape, enum values, or routes changed.")
    if missing_evidence and "No major missing evidence" not in missing_evidence[0]:
        plan.append("Resolve the missing evidence items or record an explicit manual review decision before release.")
    return plan


def _rollback_plan(
    report: ReleaseRiskReport,
    changed_files: list[dict[str, str]],
) -> list[str]:
    categories = {row["category"] for row in changed_files}
    plan = [
        "Identify the exact commit, image, or package version to restore before starting rollout.",
        "Keep the previous release artifact available until post-deploy verification is complete.",
    ]
    if "MIGRATION" in categories or "DB_MODEL" in categories:
        plan.append("Verify database rollback safety separately; schema changes may require a forward-fix, restore, or compatibility migration.")
    if "CONFIG" in categories or "DEPLOYMENT" in categories:
        plan.append("Prepare a config rollback checklist for environment variables, deployment manifests, and secrets references.")
    if "API" in categories:
        plan.append("Have an API compatibility rollback path ready for clients pinned to the previous contract.")
    if report.risk_level.value in {"HIGH", "CRITICAL"}:
        plan.append("Assign an owner to monitor the rollout and make the rollback decision quickly if leading indicators degrade.")
    return plan


def _score_breakdown(
    report: ReleaseRiskReport,
    missing_evidence: list[str],
) -> list[str]:
    return [
        f"LLM-provided readiness score: {report.release_readiness_score}/100.",
        f"LLM-provided decision: {report.decision.value}.",
        f"LLM-provided risk level: {report.risk_level.value}.",
        f"Risk finding count: {len(report.what_may_break)}.",
        f"CI blind spot count: {len(report.what_ci_may_miss)}.",
        f"Missing evidence item count: {len(missing_evidence)}.",
        "A numeric sub-score breakdown is not available in the current ShipGuard LLM schema.",
    ]


def _appendix(
    pr_summary: PRChangeSummary,
    memory: dict[str, Any],
) -> list[str]:
    return [
        f"Diff strategy: {pr_summary.diff_strategy}.",
        f"Diff context budget: {pr_summary.max_diff_chars} characters.",
        f"Full file diffs included: {len(pr_summary.included_files)}.",
        f"Partial file diffs included: {len(pr_summary.partially_included_files)}.",
        f"File diffs omitted: {len(pr_summary.omitted_files)}.",
        f"Changed file list is complete: {len(pr_summary.changed_files)} files.",
        f"Memory used: {'yes' if memory['used'] else 'no'}.",
        f"Memory summary source: {memory['summary_source']}.",
        f"Memory files indexed: {memory['indexed_files']}.",
        f"Memory tree truncated: {'yes' if memory['tree_truncated'] else 'no'}.",
    ]


def _executive_summary(report: ReleaseRiskReport, pr_summary: PRChangeSummary) -> str:
    primary_risk = report.what_may_break[0] if report.what_may_break else "No primary risk was returned."
    return (
        f"ShipGuard scored PR #{pr_summary.pr_number} at "
        f"{report.release_readiness_score}/100 with decision {report.decision.value} "
        f"and risk level {report.risk_level.value}. The leading release concern is: "
        f"{primary_risk}"
    )


def _markdown_memory(memory: dict[str, Any]) -> str:
    if not memory["used"]:
        return "- Project memory was not used for this analysis."
    lines = [
        f"- Memory directory: `{memory['memory_directory']}`",
        f"- Rebuilt this run: {memory['rebuilt']}",
        f"- Summary source: {memory['summary_source']}",
        f"- Total files discovered: {memory['total_files_discovered']}",
        f"- Files indexed: {memory['indexed_files']}",
        f"- Files skipped: {memory['files_skipped']}",
        f"- Tree truncated: {memory['tree_truncated']}",
        f"- Known categories: {memory['known_categories_count']}",
    ]
    if memory.get("architecture_summary"):
        lines.append(f"- Architecture summary: {memory['architecture_summary']}")
    if memory.get("known_release_risks"):
        lines.append("- Known release risks:")
        lines.extend(f"  - {item}" for item in memory["known_release_risks"][:6])
    return "\n".join(lines)


def _memory_html(memory: dict[str, Any]) -> str:
    if not memory["used"]:
        return "<p>Project memory was not used for this analysis.</p>"
    return (
        f"<p><strong>Source:</strong> {escape(str(memory['summary_source']))}</p>"
        f"<p><strong>Discovered:</strong> {escape(str(memory['total_files_discovered']))} files</p>"
        f"<p><strong>Indexed:</strong> {escape(str(memory['indexed_files']))} files</p>"
        f"<p><strong>Skipped:</strong> {escape(str(memory['files_skipped']))} files</p>"
        f"<p><strong>Tree truncated:</strong> {'yes' if memory['tree_truncated'] else 'no'}</p>"
        f"<p class=\"muted\">{escape(str(memory.get('architecture_summary') or 'No architecture summary saved.'))}</p>"
    )


def _changed_files_table(rows: list[dict[str, str]]) -> str:
    body = "\n".join(
        "<tr>"
        f"<td><code>{escape(row['path'])}</code></td>"
        f"<td>{escape(row['category'])}</td>"
        f"<td>{escape(row['extension'])}</td>"
        f"<td>{escape(row['diff_evidence'])}</td>"
        "</tr>"
        for row in rows
    )
    return (
        "<table><thead><tr><th>File</th><th>Category</th><th>Ext</th>"
        "<th>Diff Evidence</th></tr></thead><tbody>"
        + body
        + "</tbody></table>"
    )


def _risk_cards(items: list[str]) -> str:
    return "\n".join(f"<div class=\"risk-item\">{escape(item)}</div>" for item in items)


def _li_items(items: list[str]) -> str:
    return "\n".join(f"<li>{escape(item)}</li>" for item in items)


def _metric_card(label: str, value: object) -> str:
    return (
        "<div class=\"card span-3\">"
        f"<div class=\"metric\">{escape(str(value))}</div>"
        f"<div class=\"metric-label\">{escape(label)}</div>"
        "</div>"
    )


def _markdown_list(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items] if items else ["- None"]


def _category_counts(inventory: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in inventory:
        category = getattr(item, "final_category", "UNKNOWN")
        counts[category] = counts.get(category, 0) + 1
    return dict(sorted(counts.items()))


def _has_category(paths: list[str], categories: set[str]) -> bool:
    return any(classify_file(path) in categories for path in paths)


def _badge_class(value: str) -> str:
    return {
        "ALLOW_RELEASE": "allow",
        "REVIEW_REQUIRED": "review",
        "BLOCK_RELEASE": "block",
        "LOW": "low",
        "MEDIUM": "medium",
        "HIGH": "high",
        "CRITICAL": "critical",
    }.get(value, "review")


def _score_color(score: int) -> str:
    if score >= 80:
        return "#86efac"
    if score >= 60:
        return "#fde68a"
    return "#fca5a5"


def _report_dir_name(pr_summary: PRChangeSummary) -> str:
    owner = _safe_path_part(pr_summary.owner)
    repo = _safe_path_part(pr_summary.repo)
    return f"{owner}_{repo}_pr_{pr_summary.pr_number}"


def _safe_path_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "unknown"


def _now_utc_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
