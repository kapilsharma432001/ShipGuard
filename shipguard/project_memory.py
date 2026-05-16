from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from shipguard.models import (
    ProjectFileContext,
    ProjectMemory,
    ReleaseHistoryItem,
)


PROJECT_MEMORY_FILE = "project_memory.json"
FILES_INDEX_FILE = "files_index.json"
RELEASE_HISTORY_FILE = "release_history.jsonl"


class ProjectMemoryError(RuntimeError):
    """Raised when ShipGuard cannot read or write project memory."""


class ProjectMemoryStore:
    def __init__(self, memory_dir: Path, owner: str, repo: str) -> None:
        self.root = memory_dir
        self.owner = owner
        self.repo = repo
        self.path = memory_dir / _memory_repo_name(owner, repo)

    @property
    def project_memory_path(self) -> Path:
        return self.path / PROJECT_MEMORY_FILE

    @property
    def files_index_path(self) -> Path:
        return self.path / FILES_INDEX_FILE

    @property
    def release_history_path(self) -> Path:
        return self.path / RELEASE_HISTORY_FILE

    def ensure(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)

    def load_project_memory(self) -> ProjectMemory | None:
        if not self.project_memory_path.is_file():
            return None

        try:
            return ProjectMemory.model_validate_json(
                self.project_memory_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError) as exc:
            raise ProjectMemoryError(
                f"could not read project memory: {self.project_memory_path}"
            ) from exc

    def save_project_memory(self, memory: ProjectMemory) -> None:
        self.ensure()
        _write_json(self.project_memory_path, memory.model_dump(mode="json"))

    def load_files_index(self) -> list[ProjectFileContext]:
        if not self.files_index_path.is_file():
            return []

        try:
            raw = json.loads(self.files_index_path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                raise ValueError("files index must be a list")
            return [ProjectFileContext.model_validate(item) for item in raw]
        except (OSError, ValidationError, ValueError, json.JSONDecodeError) as exc:
            raise ProjectMemoryError(
                f"could not read files index: {self.files_index_path}"
            ) from exc

    def save_files_index(self, contexts: list[ProjectFileContext]) -> None:
        self.ensure()
        _write_json(
            self.files_index_path,
            [context.model_dump(mode="json") for context in contexts],
        )

    def load_release_history(self, limit: int = 10) -> list[ReleaseHistoryItem]:
        if not self.release_history_path.is_file():
            return []

        items: list[ReleaseHistoryItem] = []
        try:
            for line in self.release_history_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    items.append(ReleaseHistoryItem.model_validate_json(line))
        except (OSError, ValidationError, ValueError) as exc:
            raise ProjectMemoryError(
                f"could not read release history: {self.release_history_path}"
            ) from exc

        return items[-limit:]

    def append_release_history(self, item: ReleaseHistoryItem) -> None:
        self.ensure()
        with self.release_history_path.open("a", encoding="utf-8") as handle:
            handle.write(item.model_dump_json() + "\n")


def now_utc_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def merge_sorted(*values: list[str]) -> list[str]:
    merged = {item for group in values for item in group if item}
    return sorted(merged)


def _memory_repo_name(owner: str, repo: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{owner}_{repo}")


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
