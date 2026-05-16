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
    diff: str
    diff_truncated: bool
    max_diff_chars: int
