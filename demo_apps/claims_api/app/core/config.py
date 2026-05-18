import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    claims_api_token: str
    fraud_model_endpoint: str


def load_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///claims.db"),
        claims_api_token=os.environ["CLAIMS_API_TOKEN"],
        fraud_model_endpoint=os.environ["FRAUD_MODEL_ENDPOINT"],
    )
