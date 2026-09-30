from fastapi import APIRouter

from app.api.v1 import files, health, pairing, uploads

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(files.router)
api_router.include_router(health.router)
api_router.include_router(pairing.router)
api_router.include_router(uploads.router)
