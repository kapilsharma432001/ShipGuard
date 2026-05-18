from app.routes.claims import ClaimDecisionRequest, decide_claim


def test_manual_review_claim_uses_denied_decision_and_assigned_queue() -> None:
    request = ClaimDecisionRequest(
        claimant_id="CLAIMANT-123",
        claim_amount=12_500,
        diagnosis_code="X101",
    )

    response = decide_claim("claim-001", request)

    assert response.decision == "Denied"
    assert response.assigned_queue == "manual_review"
