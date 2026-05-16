from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shipguard.github_client import GitHubClient, GitHubClientError
from shipguard.llm_client import LLMClient, ShipGuardLLMError
from shipguard.models import (
    MemoryBuildReport,
    PRChangeSummary,
    ProjectFileContext,
    ProjectMemory,
    ReleaseHistoryItem,
    ReleaseRiskReport,
    RepositoryFileInventoryItem,
)
from shipguard.project_memory import (
    ProjectMemoryStore,
    merge_sorted,
    now_utc_iso,
)


MAX_FILE_BYTES = 200_000
MAX_LLM_CONTEXT_FILES = 240
LLM_BATCH_SIZE = 40
MAX_LLM_BATCH_CHARS = 45_000


@dataclass
class ProjectContextPackage:
    memory: ProjectMemory
    inventory: list[RepositoryFileInventoryItem]
    file_contexts: list[ProjectFileContext]
    build_report: MemoryBuildReport
    release_history: list[ReleaseHistoryItem]
    rebuilt: bool


def load_or_build_project_context(
    github_client: GitHubClient,
    pr_summary: PRChangeSummary,
    store: ProjectMemoryStore,
    llm_client: LLMClient | None = None,
    rebuild: bool = False,
) -> ProjectContextPackage:
    existing_memory = store.load_project_memory()
    existing_inventory = store.load_repo_inventory()
    existing_files = store.load_files_index()
    existing_report = store.load_memory_build_report()

    if (
        not rebuild
        and existing_memory is not None
        and existing_report is not None
        and existing_memory.last_indexed_base_sha == pr_summary.base_sha
        and existing_inventory
    ):
        return ProjectContextPackage(
            memory=existing_memory,
            inventory=existing_inventory,
            file_contexts=existing_files,
            build_report=existing_report,
            release_history=store.load_release_history(),
            rebuilt=False,
        )

    repo_metadata = github_client.fetch_repository_metadata(
        pr_summary.owner,
        pr_summary.repo,
    )
    default_branch = _optional_str(repo_metadata.get("default_branch"))
    tree, tree_truncated, tree_warning = github_client.fetch_repository_tree(
        pr_summary.owner,
        pr_summary.repo,
        pr_summary.base_sha,
    )

    inventory = _build_initial_inventory(tree)
    contexts: list[ProjectFileContext] = []
    inventory_by_path = {item.path: item for item in inventory}

    for item in sorted(inventory, key=lambda entry: (entry.priority, entry.path.lower())):
        reason = _content_skip_reason(item)
        if reason:
            inventory_by_path[item.path] = item.model_copy(
                update={"content_fetched": False, "skipped_reason": reason}
            )
            continue

        try:
            content = github_client.fetch_file_content(
                pr_summary.owner,
                pr_summary.repo,
                item.path,
                pr_summary.base_sha,
                max_bytes=MAX_FILE_BYTES,
            )
        except GitHubClientError:
            content = None

        if content is None:
            inventory_by_path[item.path] = item.model_copy(
                update={
                    "content_fetched": False,
                    "skipped_reason": "content unavailable or not decodable as text",
                }
            )
            continue

        context = extract_file_context(item.path, content, initial_category=item.initial_category)
        contexts.append(context)
        inventory_by_path[item.path] = item.model_copy(
            update={
                "content_fetched": True,
                "final_category": context.category,
                "priority": category_priority(context.category),
                "skipped_reason": None,
            }
        )

    final_inventory = [inventory_by_path[item.path] for item in inventory]
    memory = _build_project_memory(
        owner=pr_summary.owner,
        repo=pr_summary.repo,
        default_branch=default_branch,
        base_sha=pr_summary.base_sha,
        contexts=contexts,
        existing=existing_memory,
    )
    report = _build_report(
        owner=pr_summary.owner,
        repo=pr_summary.repo,
        base_sha=pr_summary.base_sha,
        inventory=final_inventory,
        tree_truncated=tree_truncated,
        tree_warning=tree_warning,
        llm_summary_used=False,
        llm_summary_error=None,
    )

    if llm_client is not None:
        llm_used, llm_error = _apply_llm_project_summary(memory, contexts, llm_client)
        report = report.model_copy(
            update={
                "llm_summary_used": llm_used,
                "llm_summary_error": llm_error,
            }
        )

    if not report.llm_summary_used:
        memory.summary_source = "DETERMINISTIC"

    store.save_repo_inventory(final_inventory)
    store.save_files_index(contexts)
    store.save_project_memory(memory)
    store.save_memory_build_report(report)

    return ProjectContextPackage(
        memory=memory,
        inventory=final_inventory,
        file_contexts=contexts,
        build_report=report,
        release_history=store.load_release_history(),
        rebuilt=True,
    )


def extract_file_context(
    path: str,
    content: str,
    initial_category: str | None = None,
) -> ProjectFileContext:
    env_vars = _extract_env_vars(content)
    api_routes = _extract_api_routes(content)
    db_tables = _extract_db_tables(content)
    important_symbols = _extract_symbols(content)
    imports = _extract_imports(content)
    migration_operations = _extract_migration_operations(content)
    dependencies = _extract_dependencies(path, content)
    security_signals = _extract_security_signals(path, content)
    test_frameworks = _extract_test_frameworks(path, content)
    category = refine_category_with_content(
        path=path,
        initial_category=initial_category or classify_file(path),
        content=content,
        api_routes=api_routes,
        db_tables=db_tables,
        migration_operations=migration_operations,
        security_signals=security_signals,
        test_frameworks=test_frameworks,
    )

    return ProjectFileContext(
        path=path,
        category=category,
        summary=_deterministic_summary(
            category=category,
            env_vars=env_vars,
            db_tables=db_tables,
            api_routes=api_routes,
            important_symbols=important_symbols,
            imports=imports,
            migration_operations=migration_operations,
            dependencies=dependencies,
            security_signals=security_signals,
            test_frameworks=test_frameworks,
        ),
        important_symbols=important_symbols,
        env_vars=env_vars,
        db_tables=db_tables,
        api_routes=api_routes,
        imports=imports,
        migration_operations=migration_operations,
        dependencies=dependencies,
        security_signals=security_signals,
        test_frameworks=test_frameworks,
    )


def classify_file(path: str) -> str:
    lower_path = path.lower()
    name = Path(lower_path).name
    parts = set(Path(lower_path).parts)
    extension = Path(lower_path).suffix

    if name in _DEPENDENCY_FILES or name.endswith(".lock"):
        return "DEPENDENCY"
    if _is_ci_cd_path(lower_path, name, parts):
        return "CI_CD"
    if _is_deployment_path(lower_path, name, parts):
        return "DEPLOYMENT"
    if _is_config_path(lower_path, name, parts, extension):
        return "CONFIG"
    if _is_migration_path(lower_path, name, parts):
        return "MIGRATION"
    if _is_security_path(lower_path, name, parts):
        return "SECURITY"
    if _is_test_path(lower_path, name, parts):
        return "TEST"
    if _is_api_path(lower_path, name, parts):
        return "API"
    if _is_service_path(lower_path, name, parts):
        return "SERVICE"
    if _is_db_model_path(lower_path, name, parts):
        return "DB_MODEL"
    if _is_frontend_path(lower_path, name, parts, extension):
        return "FRONTEND"
    if _is_docs_path(lower_path, name, parts):
        return "DOCS"
    if extension in _SOURCE_EXTENSIONS:
        return "SOURCE"

    return "UNKNOWN"


def refine_category_with_content(
    path: str,
    initial_category: str,
    content: str,
    api_routes: list[str],
    db_tables: list[str],
    migration_operations: list[str],
    security_signals: list[str],
    test_frameworks: list[str],
) -> str:
    if migration_operations:
        return "MIGRATION"
    if api_routes or _has_web_routing_signal(content):
        return "API"
    if db_tables or "models.Model" in content or "model " in content:
        return "DB_MODEL"
    if security_signals and initial_category in {"SOURCE", "SERVICE", "UNKNOWN"}:
        return "SECURITY"
    if test_frameworks:
        return "TEST"
    if _has_frontend_signal(path, content) and initial_category in {"SOURCE", "UNKNOWN"}:
        return "FRONTEND"
    return initial_category


def category_priority(category: str) -> int:
    return {
        "MIGRATION": 0,
        "API": 1,
        "SECURITY": 2,
        "CONFIG": 3,
        "DEPLOYMENT": 4,
        "DEPENDENCY": 5,
        "DB_MODEL": 6,
        "SERVICE": 7,
        "CI_CD": 8,
        "TEST": 9,
        "FRONTEND": 10,
        "SOURCE": 11,
        "DOCS": 12,
        "UNKNOWN": 13,
    }.get(category, 13)


def format_memory_for_prompt(
    memory: ProjectMemory,
    file_contexts: list[ProjectFileContext],
    release_history: list[ReleaseHistoryItem],
    build_report: MemoryBuildReport | None = None,
) -> str:
    recent_releases = "\n".join(
        (
            f"- PR #{item.pr_number}: {item.title} | decision={item.decision} "
            f"risk={item.risk_level} score={item.final_score} "
            f"top_risks={'; '.join(item.top_risks[:3]) or 'none'}"
        )
        for item in release_history[-5:]
    ) or "- None"
    category_counts = _category_counts(file_contexts)
    file_lines = "\n".join(
        (
            f"- {context.path} [{context.category}]: {context.summary} "
            f"env={', '.join(context.env_vars) or 'none'} "
            f"tables={', '.join(context.db_tables) or 'none'} "
            f"routes={', '.join(context.api_routes) or 'none'}"
        )
        for context in sorted(
            file_contexts,
            key=lambda item: (category_priority(item.category), item.path.lower()),
        )[:120]
    ) or "- None"
    report_text = _format_build_report_for_prompt(build_report)

    return f"""Project memory:
Repository: {memory.owner}/{memory.repo}
Default branch: {memory.default_branch or "unknown"}
Last indexed base SHA: {memory.last_indexed_base_sha or "unknown"}
Last analyzed head SHA: {memory.last_analyzed_head_sha or "unknown"}
Last updated at: {memory.last_updated_at}
Summary source: {memory.summary_source}
Architecture summary: {memory.architecture_summary or "No architecture summary saved."}
Important components: {_join(memory.important_components)}
Known API surface: {_join(memory.known_api_surface)}
Known data surface: {_join(memory.known_data_surface)}
Known config surface: {_join(memory.known_config_surface)}
Known API files: {_join(memory.known_api_files)}
Known model files: {_join(memory.known_model_files)}
Known migration files: {_join(memory.known_migration_files)}
Known config files: {_join(memory.known_config_files)}
Known test files: {_join(memory.known_test_files)}
Known dependency files: {_join(memory.known_dependency_files)}
Known env vars: {_join(memory.known_env_vars)}
Known DB tables: {_join(memory.known_db_tables)}
Known release risks: {_join(memory.known_release_risks)}
Known category counts: {category_counts}

{report_text}

Indexed project files:
{file_lines}

Recent ShipGuard release history:
{recent_releases}
"""


def format_memory_summary(package: ProjectContextPackage, store: ProjectMemoryStore) -> str:
    memory = package.memory
    report = package.build_report
    return "\n".join(
        [
            "Project Memory Summary:",
            f"- Memory directory: {store.path}",
            f"- Rebuilt this run: {package.rebuilt}",
            f"- Total files discovered: {report.total_files_discovered}",
            f"- Files content fetched: {report.files_content_fetched}",
            f"- Files skipped: {report.files_skipped}",
            f"- Tree truncated: {'yes' if report.tree_truncated else 'no'}",
            f"- Tree warning: {report.tree_truncation_warning or 'none'}",
            f"- Summary source: {memory.summary_source}",
            f"- Known categories count: {_inventory_category_counts(package.inventory)}",
            f"- Last indexed base SHA: {memory.last_indexed_base_sha or 'unknown'}",
            f"- Last analyzed head SHA: {memory.last_analyzed_head_sha or 'unknown'}",
            f"- Known previous releases: {len(package.release_history)}",
        ]
    )


def update_memory_after_analysis(
    store: ProjectMemoryStore,
    memory: ProjectMemory,
    pr_summary: PRChangeSummary,
    report: ReleaseRiskReport,
) -> ProjectMemory:
    changed_contexts = [
        ProjectFileContext(
            path=path,
            category=classify_file(path),
            summary=f"{classify_file(path)} file changed in PR.",
            important_symbols=[],
            env_vars=[],
            db_tables=[],
            api_routes=[],
        )
        for path in pr_summary.changed_files
    ]
    pr_env_vars = _extract_env_vars(pr_summary.diff)
    pr_db_tables = _extract_db_tables(pr_summary.diff)
    pr_api_routes = _extract_api_routes(pr_summary.diff)
    top_risks = report.what_may_break[:5]

    updated = memory.model_copy(
        update={
            "known_api_files": merge_sorted(
                memory.known_api_files,
                _paths_by_category(changed_contexts, "API"),
            ),
            "known_model_files": merge_sorted(
                memory.known_model_files,
                _paths_by_category(changed_contexts, "DB_MODEL"),
            ),
            "known_migration_files": merge_sorted(
                memory.known_migration_files,
                _paths_by_category(changed_contexts, "MIGRATION"),
            ),
            "known_config_files": merge_sorted(
                memory.known_config_files,
                _paths_by_categories(
                    changed_contexts,
                    {"CONFIG", "DEPLOYMENT", "CI_CD", "SECURITY"},
                ),
            ),
            "known_test_files": merge_sorted(
                memory.known_test_files,
                _paths_by_category(changed_contexts, "TEST"),
            ),
            "known_dependency_files": merge_sorted(
                memory.known_dependency_files,
                _paths_by_category(changed_contexts, "DEPENDENCY"),
            ),
            "known_env_vars": merge_sorted(memory.known_env_vars, pr_env_vars),
            "known_db_tables": merge_sorted(memory.known_db_tables, pr_db_tables),
            "known_api_surface": merge_sorted(memory.known_api_surface, pr_api_routes),
            "known_data_surface": merge_sorted(memory.known_data_surface, pr_db_tables),
            "known_config_surface": merge_sorted(memory.known_config_surface, pr_env_vars),
            "known_release_risks": merge_sorted(memory.known_release_risks, top_risks),
            "last_indexed_base_sha": pr_summary.base_sha,
            "last_analyzed_head_sha": pr_summary.head_sha,
            "last_updated_at": now_utc_iso(),
        }
    )
    store.save_project_memory(updated)
    store.append_release_history(
        ReleaseHistoryItem(
            pr_url=pr_summary.pr_url,
            pr_number=pr_summary.pr_number,
            title=pr_summary.title,
            head_sha=pr_summary.head_sha,
            generated_at=now_utc_iso(),
            final_score=report.release_readiness_score,
            decision=report.decision.value,
            risk_level=report.risk_level.value,
            top_risks=top_risks,
            changed_files=pr_summary.changed_files,
        )
    )
    return updated


def _build_initial_inventory(tree: list[dict[str, Any]]) -> list[RepositoryFileInventoryItem]:
    inventory: list[RepositoryFileInventoryItem] = []
    for item in tree:
        path = item.get("path")
        if item.get("type") != "blob" or not isinstance(path, str):
            continue
        size = item.get("size") if isinstance(item.get("size"), int) else None
        sha = item.get("sha") if isinstance(item.get("sha"), str) else None
        category = classify_file(path)
        inventory.append(
            RepositoryFileInventoryItem(
                path=path,
                sha=sha,
                size=size,
                extension=Path(path).suffix.lower() or None,
                initial_category=category,
                final_category=category,
                priority=category_priority(category),
                content_fetched=False,
                skipped_reason=None,
                is_binary_candidate=_is_binary_candidate(path),
                is_generated_candidate=_is_generated_candidate(path),
            )
        )
    return sorted(inventory, key=lambda item: item.path.lower())


def _content_skip_reason(item: RepositoryFileInventoryItem) -> str | None:
    if item.is_generated_candidate:
        return "generated or vendor/cache path skipped"
    if item.is_binary_candidate:
        return "binary candidate skipped"
    if item.size is not None and item.size > MAX_FILE_BYTES:
        return f"file larger than {MAX_FILE_BYTES} bytes"
    if not _is_text_or_code_candidate(item.path, item.final_category):
        return "not a text/code/config candidate"
    return None


def _build_project_memory(
    owner: str,
    repo: str,
    default_branch: str | None,
    base_sha: str,
    contexts: list[ProjectFileContext],
    existing: ProjectMemory | None,
) -> ProjectMemory:
    return ProjectMemory(
        owner=owner,
        repo=repo,
        default_branch=default_branch,
        last_indexed_base_sha=base_sha,
        last_analyzed_head_sha=existing.last_analyzed_head_sha if existing else None,
        architecture_summary=_deterministic_architecture_summary(contexts),
        summary_source="DETERMINISTIC",
        important_components=_top_components(contexts),
        known_api_surface=merge_sorted(*[context.api_routes for context in contexts]),
        known_data_surface=merge_sorted(*[context.db_tables for context in contexts]),
        known_config_surface=merge_sorted(*[context.env_vars for context in contexts]),
        known_api_files=_paths_by_category(contexts, "API"),
        known_model_files=_paths_by_category(contexts, "DB_MODEL"),
        known_migration_files=_paths_by_category(contexts, "MIGRATION"),
        known_config_files=_paths_by_categories(
            contexts,
            {"CONFIG", "DEPLOYMENT", "CI_CD", "SECURITY"},
        ),
        known_test_files=_paths_by_category(contexts, "TEST"),
        known_dependency_files=_paths_by_category(contexts, "DEPENDENCY"),
        known_env_vars=merge_sorted(*[context.env_vars for context in contexts]),
        known_db_tables=merge_sorted(*[context.db_tables for context in contexts]),
        known_release_risks=existing.known_release_risks if existing else [],
        last_updated_at=now_utc_iso(),
    )


def _build_report(
    owner: str,
    repo: str,
    base_sha: str,
    inventory: list[RepositoryFileInventoryItem],
    tree_truncated: bool,
    tree_warning: str | None,
    llm_summary_used: bool,
    llm_summary_error: str | None,
) -> MemoryBuildReport:
    skipped = [item for item in inventory if item.skipped_reason]
    return MemoryBuildReport(
        owner=owner,
        repo=repo,
        base_sha=base_sha,
        total_files_discovered=len(inventory),
        files_classified=len(inventory),
        files_content_fetched=sum(1 for item in inventory if item.content_fetched),
        files_skipped=len(skipped),
        binary_files_skipped=sum(1 for item in skipped if item.is_binary_candidate),
        oversized_files_skipped=sum(
            1 for item in skipped if item.skipped_reason and "larger than" in item.skipped_reason
        ),
        generated_files_skipped=sum(1 for item in skipped if item.is_generated_candidate),
        tree_truncated=tree_truncated,
        tree_truncation_warning=tree_warning,
        llm_summary_used=llm_summary_used,
        llm_summary_error=llm_summary_error,
    )


def _apply_llm_project_summary(
    memory: ProjectMemory,
    contexts: list[ProjectFileContext],
    llm_client: LLMClient,
) -> tuple[bool, str | None]:
    summaries: list[str] = []
    important_components: list[str] = []
    api_surface: list[str] = []
    data_surface: list[str] = []
    config_surface: list[str] = []
    release_risks: list[str] = []
    file_summary_updates: dict[str, str] = {}

    try:
        for batch in _context_batches(contexts):
            payload = llm_client.summarize_project_context(_format_batch_for_llm(memory, batch))
            _collect_llm_summary(
                payload,
                summaries,
                important_components,
                api_surface,
                data_surface,
                config_surface,
                release_risks,
                file_summary_updates,
            )
    except ShipGuardLLMError as exc:
        return False, str(exc)

    if not summaries and not release_risks and not file_summary_updates:
        return False, "LLM returned no usable project summary fields."

    for context in contexts:
        summary = file_summary_updates.get(context.path)
        if summary:
            context.summary = summary

    memory.architecture_summary = " ".join(summaries).strip() or memory.architecture_summary
    memory.summary_source = "LLM"
    memory.important_components = merge_sorted(memory.important_components, important_components)
    memory.known_api_surface = merge_sorted(memory.known_api_surface, api_surface)
    memory.known_data_surface = merge_sorted(memory.known_data_surface, data_surface)
    memory.known_config_surface = merge_sorted(memory.known_config_surface, config_surface)
    memory.known_release_risks = merge_sorted(memory.known_release_risks, release_risks)
    return True, None


def _collect_llm_summary(
    payload: dict[str, Any],
    summaries: list[str],
    important_components: list[str],
    api_surface: list[str],
    data_surface: list[str],
    config_surface: list[str],
    release_risks: list[str],
    file_summary_updates: dict[str, str],
) -> None:
    _append_string(payload.get("architecture_summary"), summaries)
    _extend_strings(payload.get("important_components"), important_components)
    _extend_strings(payload.get("known_api_surface"), api_surface)
    _extend_strings(payload.get("known_data_surface"), data_surface)
    _extend_strings(payload.get("known_config_surface"), config_surface)
    _extend_strings(payload.get("known_release_risks"), release_risks)

    file_summaries = payload.get("file_summaries")
    if isinstance(file_summaries, list):
        for item in file_summaries:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            summary = item.get("summary")
            if isinstance(path, str) and isinstance(summary, str) and summary.strip():
                file_summary_updates[path] = summary.strip()


def _context_batches(
    contexts: list[ProjectFileContext],
) -> list[list[ProjectFileContext]]:
    ordered = sorted(
        contexts,
        key=lambda item: (category_priority(item.category), item.path),
    )[:MAX_LLM_CONTEXT_FILES]
    batches: list[list[ProjectFileContext]] = []
    current: list[ProjectFileContext] = []
    current_size = 0
    for context in ordered:
        encoded = json.dumps(context.model_dump(mode="json"), sort_keys=True)
        if current and (len(current) >= LLM_BATCH_SIZE or current_size + len(encoded) > MAX_LLM_BATCH_CHARS):
            batches.append(current)
            current = []
            current_size = 0
        current.append(context)
        current_size += len(encoded)
    if current:
        batches.append(current)
    return batches


def _format_batch_for_llm(
    memory: ProjectMemory,
    contexts: list[ProjectFileContext],
) -> str:
    payload = {
        "repository": f"{memory.owner}/{memory.repo}",
        "base_sha": memory.last_indexed_base_sha,
        "instruction": (
            "Summarize compact extracted repository context. Do not infer from raw "
            "code beyond these deterministic signals."
        ),
        "files": [context.model_dump(mode="json") for context in contexts],
    }
    return json.dumps(payload, indent=2)[:MAX_LLM_BATCH_CHARS]


def _format_build_report_for_prompt(report: MemoryBuildReport | None) -> str:
    if report is None:
        return "Memory build report: unavailable"
    warning = report.tree_truncation_warning or "none"
    return "\n".join(
        [
            "Memory build report:",
            f"- Total files discovered: {report.total_files_discovered}",
            f"- Files classified: {report.files_classified}",
            f"- Files content fetched: {report.files_content_fetched}",
            f"- Files skipped: {report.files_skipped}",
            f"- Tree truncated: {'yes' if report.tree_truncated else 'no'}",
            f"- Tree truncation warning: {warning}",
            f"- LLM summary used: {'yes' if report.llm_summary_used else 'no'}",
            f"- LLM summary error: {report.llm_summary_error or 'none'}",
        ]
    )


def _deterministic_summary(
    category: str,
    env_vars: list[str],
    db_tables: list[str],
    api_routes: list[str],
    important_symbols: list[str],
    imports: list[str],
    migration_operations: list[str],
    dependencies: list[str],
    security_signals: list[str],
    test_frameworks: list[str],
) -> str:
    parts = [f"{category} file"]
    if api_routes:
        parts.append(f"routes: {', '.join(api_routes[:8])}")
    if db_tables:
        parts.append(f"tables/entities: {', '.join(db_tables[:8])}")
    if env_vars:
        parts.append(f"env vars: {', '.join(env_vars[:8])}")
    if migration_operations:
        parts.append(f"migration ops: {', '.join(migration_operations[:8])}")
    if dependencies:
        parts.append(f"dependencies: {', '.join(dependencies[:8])}")
    if security_signals:
        parts.append(f"security: {', '.join(security_signals[:8])}")
    if test_frameworks:
        parts.append(f"tests: {', '.join(test_frameworks[:8])}")
    if important_symbols:
        parts.append(f"symbols: {', '.join(important_symbols[:8])}")
    if imports:
        parts.append(f"imports: {', '.join(imports[:8])}")
    return "; ".join(parts) + "."


def _deterministic_architecture_summary(contexts: list[ProjectFileContext]) -> str:
    counts = _category_counts(contexts)
    if not counts:
        return "No eligible repository files were analyzed."
    return f"Repository context indexed from deterministic signals. Category counts: {counts}."


def _extract_env_vars(content: str) -> list[str]:
    patterns = [
        r"os\.environ\[\s*['\"]([A-Z][A-Z0-9_]*)['\"]\s*\]",
        r"os\.getenv\(\s*['\"]([A-Z][A-Z0-9_]*)['\"]",
        r"process\.env\.([A-Z][A-Z0-9_]*)",
        r"process\.env\[\s*['\"]([A-Z][A-Z0-9_]*)['\"]\s*\]",
        r"env\(\s*['\"]([A-Z][A-Z0-9_]*)['\"]",
        r"environ\.get\(\s*['\"]([A-Z][A-Z0-9_]*)['\"]",
        r"^([A-Z][A-Z0-9_]*)=",
    ]
    values: set[str] = set()
    for pattern in patterns:
        values.update(re.findall(pattern, content, flags=re.MULTILINE))
    return sorted(values)


def _extract_api_routes(content: str) -> list[str]:
    routes: list[str] = []
    fastapi = re.compile(
        r"@\w+\.(get|post|put|delete|patch|options|head)\(\s*['\"]([^'\"]+)['\"]",
        flags=re.IGNORECASE,
    )
    express = re.compile(
        r"\b(?:router|app)\.(get|post|put|delete|patch|use)\(\s*['\"]([^'\"]+)['\"]",
        flags=re.IGNORECASE,
    )
    django_path = re.compile(r"\b(?:path|re_path)\(\s*['\"]([^'\"]+)['\"]")
    for method, route in [*fastapi.findall(content), *express.findall(content)]:
        routes.append(f"{method.upper()} {route}")
    for route in django_path.findall(content):
        routes.append(f"DJANGO {route}")
    return _unique(routes)


def _extract_db_tables(content: str) -> list[str]:
    tables = set(re.findall(r"__tablename__\s*=\s*['\"]([^'\"]+)['\"]", content))
    tables.update(re.findall(r"db_table\s*=\s*['\"]([^'\"]+)['\"]", content))
    tables.update(re.findall(r"model\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{", content))
    migration_pattern = re.compile(
        r"op\.(?:create_table|drop_table|add_column|drop_column|alter_column)"
        r"\(\s*['\"]([^'\"]+)['\"]"
    )
    tables.update(migration_pattern.findall(content))
    return sorted(tables)


def _extract_symbols(content: str) -> list[str]:
    patterns = [
        r"^\s*(?:class|def|async\s+def)\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"^\s*(?:export\s+)?(?:function|class)\s+([A-Za-z_$][A-Za-z0-9_$]*)",
        r"^\s*(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=",
    ]
    symbols: list[str] = []
    for pattern in patterns:
        symbols.extend(re.findall(pattern, content, re.MULTILINE))
    return _unique(symbols)[:40]


def _extract_imports(content: str) -> list[str]:
    imports: list[str] = []
    patterns = [
        r"^\s*import\s+([A-Za-z0-9_., *{}$@/\-]+)",
        r"^\s*from\s+([A-Za-z0-9_./\-]+)\s+import\b",
        r"require\(\s*['\"]([^'\"]+)['\"]\s*\)",
        r"import\s+.*?\s+from\s+['\"]([^'\"]+)['\"]",
    ]
    for pattern in patterns:
        imports.extend(re.findall(pattern, content, re.MULTILINE))
    return _unique([item.strip() for item in imports if item.strip()])[:40]


def _extract_migration_operations(content: str) -> list[str]:
    operations = re.findall(
        r"\b(?:op\.)?(create_table|drop_table|add_column|drop_column|alter_column|"
        r"createIndex|dropIndex|addColumn|dropColumn|createTable|dropTable)\b",
        content,
    )
    return _unique(operations)


def _extract_dependencies(path: str, content: str) -> list[str]:
    name = Path(path.lower()).name
    dependencies: list[str] = []
    if name in {"requirements.txt", "requirements-dev.txt"}:
        for line in content.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                dependencies.append(re.split(r"[<>=~!;\[]", stripped, maxsplit=1)[0])
    elif name == "pyproject.toml":
        dependencies.extend(re.findall(r"['\"]([A-Za-z0-9_.-]+)[<>=~!]", content))
    elif name == "package.json":
        dependencies.extend(re.findall(r'"([@A-Za-z0-9_./-]+)"\s*:\s*"[^"]+"', content))
    elif name in {"pom.xml", "build.gradle", "build.gradle.kts", "go.mod", "cargo.toml"}:
        dependencies.extend(re.findall(r"['\"]?([A-Za-z0-9_.:/-]+)['\"]?\s*[:=]\s*['\"]", content))
    return _unique([item for item in dependencies if item])[:80]


def _extract_security_signals(path: str, content: str) -> list[str]:
    haystack = f"{path}\n{content}".lower()
    signals = [
        term
        for term in _SECURITY_TERMS
        if term in haystack
    ]
    return _unique(signals)


def _extract_test_frameworks(path: str, content: str) -> list[str]:
    haystack = f"{path}\n{content}".lower()
    frameworks = [
        name
        for name in ("pytest", "unittest", "jest", "vitest", "mocha", "junit", "rspec")
        if name in haystack
    ]
    if re.search(r"\bdescribe\(", content) or re.search(r"\bit\(", content):
        frameworks.append("describe/it")
    return _unique(frameworks)


def _paths_by_category(contexts: list[ProjectFileContext], category: str) -> list[str]:
    return sorted(context.path for context in contexts if context.category == category)


def _paths_by_categories(contexts: list[ProjectFileContext], categories: set[str]) -> list[str]:
    return sorted(context.path for context in contexts if context.category in categories)


def _top_components(contexts: list[ProjectFileContext]) -> list[str]:
    return [
        context.path
        for context in sorted(
            contexts,
            key=lambda item: (category_priority(item.category), item.path.lower()),
        )[:30]
    ]


def _category_counts(contexts: list[ProjectFileContext]) -> str:
    counts: dict[str, int] = {}
    for context in contexts:
        counts[context.category] = counts.get(context.category, 0) + 1
    return ", ".join(f"{key}={counts[key]}" for key in sorted(counts)) or "none"


def _inventory_category_counts(inventory: list[RepositoryFileInventoryItem]) -> str:
    counts: dict[str, int] = {}
    for item in inventory:
        category = item.final_category
        counts[category] = counts.get(category, 0) + 1
    return ", ".join(f"{key}={counts[key]}" for key in sorted(counts)) or "none"


def _join(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _append_string(value: object, target: list[str]) -> None:
    if isinstance(value, str) and value.strip():
        target.append(value.strip())


def _extend_strings(value: object, target: list[str]) -> None:
    if isinstance(value, list):
        target.extend(item.strip() for item in value if isinstance(item, str) and item.strip())


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _is_text_or_code_candidate(path: str, category: str) -> bool:
    if category != "UNKNOWN":
        return True
    extension = Path(path).suffix.lower()
    return extension in _TEXT_EXTENSIONS or extension in _SOURCE_EXTENSIONS


def _is_binary_candidate(path: str) -> bool:
    return Path(path).suffix.lower() in _BINARY_EXTENSIONS


def _is_generated_candidate(path: str) -> bool:
    lower_path = path.lower()
    parts = set(Path(lower_path).parts)
    name = Path(lower_path).name
    return bool(parts & _SKIP_DIRS) or name.endswith((".min.js", ".map", ".lockb"))


def _has_web_routing_signal(content: str) -> bool:
    return bool(
        re.search(r"\b(?:router|app)\.(?:get|post|put|delete|patch|use)\(", content)
        or "urlpatterns" in content
        or "APIRouter" in content
    )


def _has_frontend_signal(path: str, content: str) -> bool:
    extension = Path(path.lower()).suffix
    return extension in {".tsx", ".jsx", ".vue", ".svelte"} or bool(
        re.search(r"from\s+['\"](?:react|vue|@angular/)", content)
    )


def _is_ci_cd_path(lower_path: str, name: str, parts: set[str]) -> bool:
    return (
        lower_path.startswith(".github/workflows/")
        or name in {"jenkinsfile", ".gitlab-ci.yml", "azure-pipelines.yml"}
        or "ci" in parts
    )


def _is_deployment_path(lower_path: str, name: str, parts: set[str]) -> bool:
    return (
        name in {"dockerfile", "docker-compose.yml", "docker-compose.yaml", "serverless.yml"}
        or bool({"k8s", "kubernetes", "helm", "terraform", "cloudformation"} & parts)
        or lower_path.endswith((".tf", ".tfvars"))
    )


def _is_config_path(lower_path: str, name: str, parts: set[str], extension: str) -> bool:
    return (
        name.startswith(".env")
        or name in _CONFIG_FILES
        or bool({"config", "configs", "settings", "environment", "env"} & parts)
        or any(term in name for term in ("config", "settings", "environment"))
        or extension in {".yaml", ".yml", ".toml", ".ini", ".cfg"}
    )


def _is_migration_path(lower_path: str, name: str, parts: set[str]) -> bool:
    return (
        bool({"migrations", "migration", "alembic", "versions", "migrate"} & parts)
        or "migration" in lower_path
        or bool(re.match(r"v\d+__.*\.sql$", name))
        or bool(re.match(r"\d+[_-].*\.(sql|py|js|ts)$", name))
    )


def _is_security_path(lower_path: str, name: str, parts: set[str]) -> bool:
    return bool({"auth", "oauth", "security", "permission", "permissions", "rbac", "policy"} & parts) or any(
        term in lower_path for term in _SECURITY_TERMS
    )


def _is_test_path(lower_path: str, name: str, parts: set[str]) -> bool:
    return (
        bool({"test", "tests", "__tests__", "spec", "specs"} & parts)
        or name.startswith("test_")
        or name.endswith(("_test.py", ".test.js", ".test.ts", ".spec.js", ".spec.ts"))
    )


def _is_api_path(lower_path: str, name: str, parts: set[str]) -> bool:
    return (
        lower_path.startswith("api/")
        or "/api/" in lower_path
        or bool({"api", "routes", "controllers", "views", "serializers", "schemas", "endpoints"} & parts)
        or any(term in name for term in ("route", "controller", "view", "serializer", "schema", "endpoint"))
    )


def _is_service_path(lower_path: str, name: str, parts: set[str]) -> bool:
    return bool({"services", "service", "business", "domain", "usecases", "handlers"} & parts) or any(
        term in name for term in ("service", "handler", "usecase")
    )


def _is_db_model_path(lower_path: str, name: str, parts: set[str]) -> bool:
    return bool({"models", "model", "entities", "entity", "repositories", "repository"} & parts) or any(
        term in name for term in ("model", "entity", "repository")
    )


def _is_frontend_path(lower_path: str, name: str, parts: set[str], extension: str) -> bool:
    return (
        extension in {".tsx", ".jsx", ".vue", ".svelte"}
        or bool({"components", "component", "pages", "frontend", "ui"} & parts)
        or name.endswith((".component.ts", ".page.ts"))
    )


def _is_docs_path(lower_path: str, name: str, parts: set[str]) -> bool:
    return name.startswith("readme") or bool({"doc", "docs", "documentation"} & parts) or lower_path.endswith((".md", ".rst"))


_DEPENDENCY_FILES = {
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "poetry.lock",
    "pdm.lock",
    "pipfile",
    "pipfile.lock",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "uv.lock",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "go.mod",
    "go.sum",
    "cargo.toml",
    "cargo.lock",
}

_CONFIG_FILES = {
    ".env.example",
    "appsettings.json",
    "settings.json",
    "config.json",
    "config.yaml",
    "config.yml",
}

_SECURITY_TERMS = {
    "auth",
    "oauth",
    "jwt",
    "token",
    "permission",
    "permissions",
    "rbac",
    "policy",
    "encryption",
    "secret",
    "secrets",
}

_SKIP_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "target",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "coverage",
    ".next",
    ".turbo",
    "vendor",
    "vendors",
}

_SOURCE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".cs",
    ".kt",
    ".swift",
    ".sql",
    ".prisma",
}

_TEXT_EXTENSIONS = {
    ".md",
    ".rst",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".xml",
    ".html",
    ".css",
    ".scss",
    ".sh",
}

_BINARY_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".class",
    ".dll",
    ".dylib",
    ".gif",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".pyc",
    ".so",
    ".webp",
    ".zip",
}
