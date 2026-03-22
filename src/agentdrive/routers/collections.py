import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from agentdrive.db.session import get_session
from agentdrive.dependencies import get_current_tenant
from agentdrive.models.collection import Collection
from agentdrive.models.tenant import Tenant
from agentdrive.schemas.collections import CollectionCreate, CollectionListResponse, CollectionResponse

router = APIRouter(prefix="/v1/collections", tags=["collections"])

@router.post("", status_code=201, response_model=CollectionResponse)
async def create_collection(
    body: CollectionCreate,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    collection = Collection(tenant_id=tenant.id, name=body.name, description=body.description)
    session.add(collection)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail=f"Collection '{body.name}' already exists")
    await session.refresh(collection)
    return CollectionResponse.model_validate(collection)

@router.get("", response_model=CollectionListResponse)
async def list_collections(
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Collection).where(Collection.tenant_id == tenant.id).order_by(Collection.created_at)
    )
    collections = result.scalars().all()
    return CollectionListResponse(
        collections=[CollectionResponse.model_validate(c) for c in collections],
        total=len(collections),
    )

@router.delete("/{collection_id}", status_code=204)
async def delete_collection(
    collection_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Collection).where(Collection.id == collection_id, Collection.tenant_id == tenant.id)
    )
    collection = result.scalar_one_or_none()
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    await session.delete(collection)
    await session.commit()
