def choose_claim_queue(
    claimant_id: str,
    claim_amount: float,
    diagnosis_code: str,
) -> str:
    if claim_amount > 10_000 or diagnosis_code.startswith("X"):
        return "manual_review"
    if claimant_id.startswith("VIP"):
        return "priority_review"
    return "standard_review"
