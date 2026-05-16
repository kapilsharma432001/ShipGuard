import json
import os
from typing import Any

from openai import OpenAI, OpenAIError
from pydantic import ValidationError

from shipguard.models import LLMConfig, ReleaseRiskReport


class ShipGuardConfigError(RuntimeError):
    """Raised when required ShipGuard configuration is missing."""


class ShipGuardLLMError(RuntimeError):
    """Raised when the configured LLM cannot return a usable analysis."""


class LLMClient:
    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._client = OpenAI(
            base_url=str(config.base_url),
            api_key=config.api_key,
        )

    @classmethod
    def from_env(cls) -> "LLMClient":
        required_vars = {
            "SHIPGUARD_LLM_BASE_URL": os.getenv("SHIPGUARD_LLM_BASE_URL", "").strip(),
            "SHIPGUARD_LLM_API_KEY": os.getenv("SHIPGUARD_LLM_API_KEY", "").strip(),
            "SHIPGUARD_LLM_MODEL": os.getenv("SHIPGUARD_LLM_MODEL", "").strip(),
        }
        missing = [name for name, value in required_vars.items() if not value]
        if missing:
            names = ", ".join(missing)
            raise ShipGuardConfigError(
                f"missing required environment variable(s): {names}. "
                "Set SHIPGUARD_LLM_BASE_URL, SHIPGUARD_LLM_API_KEY, and "
                "SHIPGUARD_LLM_MODEL before running ShipGuard."
            )

        try:
            config = LLMConfig(
                base_url=required_vars["SHIPGUARD_LLM_BASE_URL"],
                api_key=required_vars["SHIPGUARD_LLM_API_KEY"],
                model=required_vars["SHIPGUARD_LLM_MODEL"],
            )
        except ValidationError as exc:
            raise ShipGuardConfigError(
                "invalid LLM configuration. Check SHIPGUARD_LLM_BASE_URL, "
                "SHIPGUARD_LLM_API_KEY, and SHIPGUARD_LLM_MODEL."
            ) from exc
        return cls(config)

    def analyze_release(self, release_context: str) -> ReleaseRiskReport:
        try:
            response = self._client.chat.completions.create(
                model=self._config.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are ShipGuard, an AI release risk reasoner. "
                            "Analyze release risk from the supplied repository "
                            "metadata and git diff. Focus on backward "
                            "compatibility, database migration safety, config "
                            "drift, business logic regressions, rollback risk, "
                            "and what CI may miss. "
                            "Return only valid JSON matching this schema: "
                            "{"
                            '"release_readiness_score": integer 0-100, '
                            '"decision": "ALLOW_RELEASE" | "REVIEW_REQUIRED" | '
                            '"BLOCK_RELEASE", '
                            '"risk_level": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL", '
                            '"what_may_break": array of strings, '
                            '"what_ci_may_miss": array of strings'
                            "}"
                        ),
                    },
                    {"role": "user", "content": release_context},
                ],
                temperature=0,
            )
        except OpenAIError as exc:
            raise ShipGuardLLMError(
                "LLM request failed. Check the base URL, API key, model name, "
                "and gateway availability."
            ) from exc

        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise ShipGuardLLMError("LLM returned an empty response.")

        try:
            payload = _load_json_object(content)
            return ReleaseRiskReport.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            raise ShipGuardLLMError(
                "LLM response was not valid ShipGuard JSON. Try a model with "
                "stronger instruction following or inspect the gateway response."
            ) from exc


def _load_json_object(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
        cleaned = cleaned.removesuffix("```").strip()

    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("expected a JSON object")
    return parsed
