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
