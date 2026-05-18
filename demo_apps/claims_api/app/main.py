from fastapi import FastAPI

from app.routes.claims import router as claims_router


app = FastAPI(title="Fake Claims API")
app.include_router(claims_router, prefix="/claims", tags=["claims"])
