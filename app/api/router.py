from fastapi import APIRouter

from app.api.v1 import auth, reports, summaries

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(summaries.router)
api_router.include_router(reports.router)
