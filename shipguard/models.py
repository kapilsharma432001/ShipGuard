from enum import StrEnum

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator


class Decision(StrEnum):
    GO = "GO"
    NO_GO = "NO_GO"
    GO_WITH_CAUTION = "GO_WITH_CAUTION"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


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
