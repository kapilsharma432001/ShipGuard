from sqlalchemy import Column, Float, Integer, String
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class Claim(Base):
    __tablename__ = "claims"

    id = Column(Integer, primary_key=True)
    member_id = Column(String(64), nullable=False)
    claim_amount = Column(Float, nullable=False)
    diagnosis_code = Column(String(32), nullable=False)
    decision = Column(String(32), nullable=False)
    review_queue = Column(String(64), nullable=False)
    claim_source = Column(String(32), nullable=False)
