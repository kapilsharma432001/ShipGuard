from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shipguard.github_client import GitHubClient
from shipguard.llm_client import LLMClient, ShipGuardLLMError
from shipguard.models import (
    PRChangeSummary,
    ProjectFileContext,
    ProjectMemory,
    ReleaseHistoryItem,
    ReleaseRiskReport,
)
from shipguard.project_memory import (
    ProjectMemoryStore,
    merge_sorted,
    now_utc_iso,
)


MAX_FILE_BYTES = 200_000
MAX_CONTEXT_FILES = 80
MAX_LLM_CONTEXT_CHARS = 50_000


@dataclass
class ProjectContextPackage:
    memory: ProjectMemory
    file_contexts: list[ProjectFileContext]
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
    existing_files = store.load_files_index()

    if (
        not rebuild
        and existing_memory is not None
        and existing_memory.last_indexed_base_sha == pr_summary.base_sha
        and existing_files
    ):
        return ProjectContextPackage(
            memory=existing_memory,
            file_contexts=existing_files,
            release_history=store.load_release_history(),
            rebuilt=False,
        )

    repo_metadata = github_client.fetch_repository_metadata(
        pr_summary.owner,
        pr_summary.repo,
    )
    default_branch = _optional_str(repo_metadata.get("default_branch"))
    tree = github_client.fetch_recursive_tree(
        pr_summary.owner,
        pr_summary.repo,
        pr_summary.base_sha,
    )
    selected_paths = _select_context_files(tree)

    contexts: list[ProjectFileContext] = []
    for path in selected_paths:
        content = github_client.fetch_file_content(
            pr_summary.owner,
            pr_summary.repo,
            path,
            pr_summary.base_sha,
            max_bytes=MAX_FILE_BYTES,
        )
        if content is None:
            continue
        contexts.append(extract_file_context(path, content))

    memory = _build_project_memory(
        owner=pr_summary.owner,
        repo=pr_summary.repo,
        default_branch=default_branch,
        base_sha=pr_summary.base_sha,
        contexts=contexts,
        existing=existing_memory,
    )
    if llm_client is not None:
        _apply_llm_project_summary(memory, contexts, llm_client)

    store.save_project_memory(memory)
    store.save_files_index(contexts)

    return ProjectContextPackage(
        memory=memory,
        file_contexts=contexts,
        release_history=store.load_release_history(),
        rebuilt=True,
    )


def extract_file_context(path: str, content: str) -> ProjectFileContext:
    category = classify_file(path)
    env_vars = _extract_env_vars(content)
    db_tables = _extract_db_tables(content)
    api_routes = _extract_api_routes(content)
    important_symbols = _extract_symbols(content)

    return ProjectFileContext(
        path=path,
        category=category,
        summary=_deterministic_summary(
            category=category,
            env_vars=env_vars,
            db_tables=db_tables,
            api_routes=api_routes,
            important_symbols=important_symbols,
        ),
        important_symbols=important_symbols,
        env_vars=env_vars,
        db_tables=db_tables,
        api_routes=api_routes,
    )


def classify_file(path: str) -> str:
    lower_path = path.lower()
    name = Path(lower_path).name
    parts = set(Path(lower_path).parts)

    if {"migrations", "alembic", "versions"} & parts or "migration" in lower_path:
        return "MIGRATION"
    if name in _DEPENDENCY_FILES or name.endswith(".lock"):
        return "DEPENDENCY"
    if (
        name.startswith(".env")
        or name in {"dockerfile", "docker-compose.yml", "docker-compose.yaml"}
        or {"config", "settings", "env", "docker", "deployment"} & parts
        or any(term in name for term in ("config", "settings", "env"))
        or "deploy" in lower_path
    ):
        return "CONFIG"
    if {"test", "tests"} & parts or name.startswith("test_") or name.endswith("_test.py"):
        return "TEST"
    if (
        lower_path.startswith("api/")
        or "/api/" in lower_path
        or {"routes", "schemas", "pydantic"} & parts
        or "schema" in name
        or "route" in name
    ):
        return "API"
    if {"model", "models", "db", "database"} & parts or "model" in name:
        return "MODEL"
    if name.startswith("readme") or {"doc", "docs", "documentation"} & parts:
        return "DOCS"
    if lower_path.endswith((".md", ".rst", ".txt")):
        return "DOCS"

    return "OTHER"


def format_memory_for_prompt(
    memory: ProjectMemory,
    file_contexts: list[ProjectFileContext],
    release_history: list[ReleaseHistoryItem],
) -> str:
    recent_releases = "\n".join(
        (
            f"- PR #{item.pr_number}: {item.title} | decision={item.decision} "
            f"risk={item.risk_level} score={item.final_score} "
            f"top_risks={'; '.join(item.top_risks[:3]) or 'none'}"
        )
        for item in release_history[-5:]
    ) or "- None"

    file_lines = "\n".join(
        (
            f"- {context.path} [{context.category}]: {context.summary} "
            f"env={', '.join(context.env_vars) or 'none'} "
            f"tables={', '.join(context.db_tables) or 'none'} "
            f"routes={', '.join(context.api_routes) or 'none'}"
        )
        for context in file_contexts[:MAX_CONTEXT_FILES]
    ) or "- None"

    return f"""Project memory:
Repository: {memory.owner}/{memory.repo}
Default branch: {memory.default_branch or "unknown"}
Last indexed base SHA: {memory.last_indexed_base_sha or "unknown"}
Last analyzed head SHA: {memory.last_analyzed_head_sha or "unknown"}
Last updated at: {memory.last_updated_at}
Architecture summary: {memory.architecture_summary or "No LLM architecture summary saved."}
Known API files: {_join(memory.known_api_files)}
Known model files: {_join(memory.known_model_files)}
Known migration files: {_join(memory.known_migration_files)}
Known config files: {_join(memory.known_config_files)}
Known test files: {_join(memory.known_test_files)}
Known dependency files: {_join(memory.known_dependency_files)}
Known env vars: {_join(memory.known_env_vars)}
Known DB tables: {_join(memory.known_db_tables)}
Known release risks: {_join(memory.known_release_risks)}

Indexed project files:
{file_lines}

Recent ShipGuard release history:
{recent_releases}
"""


def format_memory_summary(package: ProjectContextPackage, store: ProjectMemoryStore) -> str:
    memory = package.memory
    return "\n".join(
        [
            "Project Memory Summary:",
            f"- Directory: {store.path}",
            f"- Rebuilt this run: {package.rebuilt}",
            f"- Last indexed base SHA: {memory.last_indexed_base_sha or 'unknown'}",
            f"- Last analyzed head SHA: {memory.last_analyzed_head_sha or 'unknown'}",
            f"- Indexed files: {len(package.file_contexts)}",
            f"- Known env vars: {len(memory.known_env_vars)}",
            f"- Known DB tables: {len(memory.known_db_tables)}",
            f"- Known previous releases: {len(package.release_history)}",
            f"- Architecture summary: {memory.architecture_summary or 'not available'}",
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
    top_risks = report.what_may_break[:5]

    updated = memory.model_copy(
        update={
            "known_api_files": merge_sorted(
                memory.known_api_files,
                _paths_by_category(changed_contexts, "API"),
            ),
            "known_model_files": merge_sorted(
                memory.known_model_files,
                _paths_by_category(changed_contexts, "MODEL"),
            ),
            "known_migration_files": merge_sorted(
                memory.known_migration_files,
                _paths_by_category(changed_contexts, "MIGRATION"),
            ),
            "known_config_files": merge_sorted(
                memory.known_config_files,
                _paths_by_category(changed_contexts, "CONFIG"),
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


def _build_project_memory(
    owner: str,
    repo: str,
    default_branch: str | None,
    base_sha: str,
    contexts: list[ProjectFileContext],
    existing: ProjectMemory | None,
) -> ProjectMemory:
    known_risks = existing.known_release_risks if existing else []
    return ProjectMemory(
        owner=owner,
        repo=repo,
        default_branch=default_branch,
        last_indexed_base_sha=base_sha,
        last_analyzed_head_sha=existing.last_analyzed_head_sha if existing else None,
        architecture_summary=existing.architecture_summary if existing else None,
        known_api_files=_paths_by_category(contexts, "API"),
        known_model_files=_paths_by_category(contexts, "MODEL"),
        known_migration_files=_paths_by_category(contexts, "MIGRATION"),
        known_config_files=_paths_by_category(contexts, "CONFIG"),
        known_test_files=_paths_by_category(contexts, "TEST"),
        known_dependency_files=_paths_by_category(contexts, "DEPENDENCY"),
        known_env_vars=merge_sorted(*[context.env_vars for context in contexts]),
        known_db_tables=merge_sorted(*[context.db_tables for context in contexts]),
        known_release_risks=known_risks,
        last_updated_at=now_utc_iso(),
    )


def _apply_llm_project_summary(
    memory: ProjectMemory,
    contexts: list[ProjectFileContext],
    llm_client: LLMClient,
) -> None:
    try:
        payload = llm_client.summarize_project_context(
            _format_context_summary_for_llm(memory, contexts)
        )
    except ShipGuardLLMError:
        return

    architecture_summary = payload.get("architecture_summary")
    if isinstance(architecture_summary, str) and architecture_summary.strip():
        memory.architecture_summary = architecture_summary.strip()

    known_release_risks = payload.get("known_release_risks")
    if isinstance(known_release_risks, list):
        memory.known_release_risks = merge_sorted(
            memory.known_release_risks,
            [item for item in known_release_risks if isinstance(item, str)],
        )

    file_summaries = payload.get("file_summaries")
    if isinstance(file_summaries, list):
        summaries_by_path = {
            item.get("path"): item.get("summary")
            for item in file_summaries
            if isinstance(item, dict)
        }
        for context in contexts:
            summary = summaries_by_path.get(context.path)
            if isinstance(summary, str) and summary.strip():
                context.summary = summary.strip()


def _format_context_summary_for_llm(
    memory: ProjectMemory,
    contexts: list[ProjectFileContext],
) -> str:
    files = []
    for context in contexts[:MAX_CONTEXT_FILES]:
        files.append(
            {
                "path": context.path,
                "category": context.category,
                "summary": context.summary,
                "important_symbols": context.important_symbols[:20],
                "env_vars": context.env_vars,
                "db_tables": context.db_tables,
                "api_routes": context.api_routes,
            }
        )

    payload = {
        "repository": f"{memory.owner}/{memory.repo}",
        "base_sha": memory.last_indexed_base_sha,
        "known_env_vars": memory.known_env_vars,
        "known_db_tables": memory.known_db_tables,
        "files": files,
    }
    return json.dumps(payload, indent=2)[:MAX_LLM_CONTEXT_CHARS]


def _select_context_files(tree: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for item in tree:
        path = item.get("path")
        if item.get("type") != "blob" or not isinstance(path, str):
            continue
        size = item.get("size")
        if isinstance(size, int) and size > MAX_FILE_BYTES:
            continue
        if _is_probably_binary_path(path):
            continue
        if classify_file(path) == "OTHER":
            continue
        paths.append(path)

    return sorted(paths, key=_selection_priority)[:MAX_CONTEXT_FILES]


def _selection_priority(path: str) -> tuple[int, str]:
    lower_path = path.lower()
    name = Path(lower_path).name
    category = classify_file(path)
    if name == "readme.md":
        return (0, lower_path)
    priority = {
        "DEPENDENCY": 1,
        "API": 2,
        "MIGRATION": 3,
        "CONFIG": 4,
        "MODEL": 5,
        "TEST": 6,
        "DOCS": 7,
    }.get(category, 8)
    return (priority, lower_path)


def _deterministic_summary(
    category: str,
    env_vars: list[str],
    db_tables: list[str],
    api_routes: list[str],
    important_symbols: list[str],
) -> str:
    parts = [f"{category} file"]
    if api_routes:
        parts.append(f"routes: {', '.join(api_routes[:8])}")
    if db_tables:
        parts.append(f"tables: {', '.join(db_tables[:8])}")
    if env_vars:
        parts.append(f"env vars: {', '.join(env_vars[:8])}")
    if important_symbols:
        parts.append(f"symbols: {', '.join(important_symbols[:8])}")
    return "; ".join(parts) + "."


def _extract_env_vars(content: str) -> list[str]:
    patterns = [
        r"os\.environ\[\s*['\"]([A-Z][A-Z0-9_]*)['\"]\s*\]",
        r"os\.getenv\(\s*['\"]([A-Z][A-Z0-9_]*)['\"]",
        r"environ\.get\(\s*['\"]([A-Z][A-Z0-9_]*)['\"]",
        r"^([A-Z][A-Z0-9_]*)=",
    ]
    values: set[str] = set()
    for pattern in patterns:
        values.update(re.findall(pattern, content, flags=re.MULTILINE))
    return sorted(values)


def _extract_api_routes(content: str) -> list[str]:
    routes: list[str] = []
    pattern = re.compile(
        r"@\w+\.(get|post|put|delete|patch|options|head)\(\s*['\"]([^'\"]+)['\"]",
        flags=re.IGNORECASE,
    )
    for method, route in pattern.findall(content):
        routes.append(f"{method.upper()} {route}")
    return _unique(routes)


def _extract_db_tables(content: str) -> list[str]:
    tables = set(re.findall(r"__tablename__\s*=\s*['\"]([^'\"]+)['\"]", content))
    migration_pattern = re.compile(
        r"op\.(?:create_table|drop_table|add_column|drop_column|alter_column)"
        r"\(\s*['\"]([^'\"]+)['\"]"
    )
    tables.update(migration_pattern.findall(content))
    return sorted(tables)


def _extract_symbols(content: str) -> list[str]:
    symbols = re.findall(
        r"^\s*(?:class|def)\s+([A-Za-z_][A-Za-z0-9_]*)",
        content,
        re.MULTILINE,
    )
    return _unique(symbols)[:25]


def _paths_by_category(contexts: list[ProjectFileContext], category: str) -> list[str]:
    return sorted(context.path for context in contexts if context.category == category)


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


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _is_probably_binary_path(path: str) -> bool:
    return Path(path).suffix.lower() in _BINARY_EXTENSIONS


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
    "go.mod",
    "go.sum",
    "cargo.toml",
    "cargo.lock",
}

_BINARY_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".so",
    ".webp",
    ".zip",
}
