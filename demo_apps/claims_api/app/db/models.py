from sqlalchemy import Column, Float, Integer, String
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class Claim(Base):
    __tablename__ = "claims"

    id = Column(Integer, primary_key=True)
    claimant_id = Column(String(64), nullable=False)
    claim_amount = Column(Float, nullable=False)
    diagnosis_code = Column(String(32), nullable=False)
    decision = Column(String(32), nullable=False)
    assigned_queue = Column(String(64), nullable=False)
