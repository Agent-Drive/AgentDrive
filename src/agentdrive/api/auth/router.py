from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.config import settings
from agentdrive.engine.data.session import get_session
from agentdrive.api.auth import service
from agentdrive.api.auth.schemas import ExchangeRequest, ExchangeResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/config")
async def auth_config():
    """Public endpoint — returns client_id for CLI device flow."""
    if not settings.workos_client_id:
        raise HTTPException(status_code=503, detail="WorkOS not configured")
    return {"client_id": settings.workos_client_id}


@router.post("/exchange", response_model=ExchangeResponse)
async def exchange_token(
    body: ExchangeRequest,
    session: AsyncSession = Depends(get_session),
):
    return await service.exchange_token(session, body)
