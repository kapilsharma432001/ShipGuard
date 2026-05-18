from app.routes.claims import ClaimDecisionRequest, decide_claim


def test_manual_review_claim_uses_denied_decision_and_review_queue() -> None:
    request = ClaimDecisionRequest(
        member_id="CLAIMANT-123",
        claim_amount=12_500,
        diagnosis_code="X101",
    )

    response = decide_claim("claim-001", request)

    assert response.decision == "DENIED"
    assert response.review_queue == "manual_review"
