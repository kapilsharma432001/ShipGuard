import os


def choose_claim_queue(
    member_id: str,
    claim_amount: float,
    diagnosis_code: str,
) -> str:
    fraud_model_endpoint = os.getenv("FRAUD_MODEL_ENDPOINT")
    if claim_amount > 10_000 or diagnosis_code.startswith("X"):
        return "fraud_model_review" if fraud_model_endpoint else "manual_review"
    if member_id.startswith("VIP"):
        return "priority_review"
    return "standard_review"
