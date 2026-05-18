from enum import StrEnum

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.claims import choose_claim_queue


router = APIRouter()


class ClaimDecision(StrEnum):
    APPROVED = "Approved"
    DENIED = "Denied"


class ClaimDecisionRequest(BaseModel):
    claimant_id: str = Field(min_length=3)
    claim_amount: float = Field(gt=0)
    diagnosis_code: str


class ClaimDecisionResponse(BaseModel):
    claim_id: str
    decision: ClaimDecision
    assigned_queue: str


@router.post("/{claim_id}/decision", response_model=ClaimDecisionResponse)
def decide_claim(claim_id: str, request: ClaimDecisionRequest) -> ClaimDecisionResponse:
    queue = choose_claim_queue(
        claimant_id=request.claimant_id,
        claim_amount=request.claim_amount,
        diagnosis_code=request.diagnosis_code,
    )
    decision = ClaimDecision.DENIED if queue == "manual_review" else ClaimDecision.APPROVED
    return ClaimDecisionResponse(
        claim_id=claim_id,
        decision=decision,
        assigned_queue=queue,
    )
