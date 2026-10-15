from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1", tags=["content"])


class ConfigResponse(BaseModel):
    app_name: str
    version: str


@router.get("/config", response_model=ConfigResponse)
async def get_config():
    return ConfigResponse(app_name="Soft Limit", version="0.1.0")
