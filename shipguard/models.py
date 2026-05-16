from enum import StrEnum

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator


class Decision(StrEnum):
    ALLOW_RELEASE = "ALLOW_RELEASE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCK_RELEASE = "BLOCK_RELEASE"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class LLMConfig(BaseModel):
    base_url: AnyHttpUrl
    api_key: str
    model: str

    @field_validator("api_key", "model", mode="before")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("must not be blank")
        return value.strip()


class ReleaseRiskReport(BaseModel):
    release_readiness_score: int = Field(ge=0, le=100)
    decision: Decision
    risk_level: RiskLevel
    what_may_break: list[str] = Field(min_length=1)
    what_ci_may_miss: list[str] = Field(min_length=1)


class GitChangeSummary(BaseModel):
    repo_path: str
    current_branch: str | None = None
    latest_commit_hash: str | None = None
    has_uncommitted_changes: bool
    changed_files: list[str]
    changed_file_extensions: list[str]
    diff_stat: str
    diff: str
    diff_truncated: bool
    max_diff_chars: int


class GitHubPRRef(BaseModel):
    owner: str
    repo: str
    number: int
    url: str


class PRChangeSummary(BaseModel):
    pr_url: str
    owner: str
    repo: str
    pr_number: int
    title: str
    body: str | None = None
    state: str
    base_branch: str
    head_branch: str
    base_sha: str
    head_sha: str
    changed_files_count: int
    additions: int
    deletions: int
    changed_files: list[str]
    changed_file_extensions: list[str]
    included_files: list[str]
    omitted_files: list[str]
    partially_included_files: list[str]
    diff_strategy: str
    diff: str
    diff_truncated: bool
    max_diff_chars: int


class ProjectMemory(BaseModel):
    owner: str
    repo: str
    default_branch: str | None = None
    last_indexed_base_sha: str | None = None
    last_analyzed_head_sha: str | None = None
    architecture_summary: str | None = None
    summary_source: str = "DETERMINISTIC"
    important_components: list[str] = Field(default_factory=list)
    known_api_surface: list[str] = Field(default_factory=list)
    known_data_surface: list[str] = Field(default_factory=list)
    known_config_surface: list[str] = Field(default_factory=list)
    known_api_files: list[str] = Field(default_factory=list)
    known_model_files: list[str] = Field(default_factory=list)
    known_migration_files: list[str] = Field(default_factory=list)
    known_config_files: list[str] = Field(default_factory=list)
    known_test_files: list[str] = Field(default_factory=list)
    known_dependency_files: list[str] = Field(default_factory=list)
    known_env_vars: list[str] = Field(default_factory=list)
    known_db_tables: list[str] = Field(default_factory=list)
    known_release_risks: list[str] = Field(default_factory=list)
    last_updated_at: str


class ProjectFileContext(BaseModel):
    path: str
    category: str
    summary: str
    important_symbols: list[str] = Field(default_factory=list)
    env_vars: list[str] = Field(default_factory=list)
    db_tables: list[str] = Field(default_factory=list)
    api_routes: list[str] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=list)
    migration_operations: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    security_signals: list[str] = Field(default_factory=list)
    test_frameworks: list[str] = Field(default_factory=list)


class ReleaseHistoryItem(BaseModel):
    pr_url: str
    pr_number: int
    title: str
    head_sha: str
    generated_at: str
    final_score: int | None = None
    decision: str | None = None
    risk_level: str | None = None
    top_risks: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)


class RepositoryFileInventoryItem(BaseModel):
    path: str
    sha: str | None = None
    size: int | None = None
    extension: str | None = None
    initial_category: str
    final_category: str
    priority: int
    content_fetched: bool
    skipped_reason: str | None = None
    is_binary_candidate: bool
    is_generated_candidate: bool


class MemoryBuildReport(BaseModel):
    owner: str
    repo: str
    base_sha: str
    total_files_discovered: int
    files_classified: int
    files_content_fetched: int
    files_skipped: int
    binary_files_skipped: int
    oversized_files_skipped: int
    generated_files_skipped: int
    tree_truncated: bool
    tree_truncation_warning: str | None = None
    llm_summary_used: bool
    llm_summary_error: str | None = None
