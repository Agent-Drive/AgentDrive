import asyncio
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from agentdrive.db.session import get_session
from agentdrive.dependencies import get_current_tenant
from agentdrive.knowledge.compilation.pipeline import compile_kb
from agentdrive.knowledge.models import Article, KnowledgeBase
from agentdrive.knowledge.schemas import (
    ArticleListResponse,
    ArticleResponse,
    KBAddFilesRequest,
    KBCreateRequest,
    KBListResponse,
    KBRemoveFilesRequest,
    KBResponse,
    KBSearchRequest,
    KBSearchResponse,
    KBSearchResultResponse,
)
from agentdrive.knowledge.service import KBService
from agentdrive.models.tenant import Tenant
from agentdrive.search.engine import SearchEngine

router = APIRouter(prefix="/v1/knowledge-bases", tags=["knowledge-bases"])

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = SearchEngine()
    return _engine


async def _build_kb_response(svc: KBService, kb: KnowledgeBase) -> KBResponse:
    """Build a KBResponse with file and article counts."""
    file_count = await svc.get_file_count(kb.id)
    article_count = await svc.get_article_count(kb.id)
    return KBResponse(
        id=kb.id,
        name=kb.name,
        description=kb.description,
        status=kb.status,
        config=kb.config,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
        file_count=file_count,
        article_count=article_count,
    )


@router.post("", status_code=201, response_model=KBResponse)
async def create_knowledge_base(
    body: KBCreateRequest,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    svc = KBService(session)
    try:
        kb = await svc.create(
            tenant_id=tenant.id,
            name=body.name,
            description=body.description,
            config=body.config.model_dump() if body.config else {},
        )
        await session.commit()
        await session.refresh(kb)
    except ValueError:
        raise HTTPException(
            status_code=409,
            detail=f"Knowledge base with name '{body.name}' already exists",
        )
    return await _build_kb_response(svc, kb)


@router.get("", response_model=KBListResponse)
async def list_knowledge_bases(
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    svc = KBService(session)
    kbs = await svc.list(tenant_id=tenant.id)
    responses = [await _build_kb_response(svc, kb) for kb in kbs]
    return KBListResponse(knowledge_bases=responses, total=len(responses))


@router.get("/{kb_id}", response_model=KBResponse)
async def get_knowledge_base(
    kb_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    svc = KBService(session)
    kb = await svc.get(tenant_id=tenant.id, kb_id=kb_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return await _build_kb_response(svc, kb)


@router.delete("/{kb_id}", status_code=204)
async def delete_knowledge_base(
    kb_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    svc = KBService(session)
    kb = await svc.get(tenant_id=tenant.id, kb_id=kb_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    await svc.delete(tenant_id=tenant.id, kb_id=kb_id)
    await session.commit()


@router.post("/{kb_id}/files", status_code=200)
async def add_files_to_kb(
    kb_id: uuid.UUID,
    body: KBAddFilesRequest,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    svc = KBService(session)
    try:
        added = await svc.add_files(
            tenant_id=tenant.id, kb_id=kb_id, file_ids=body.file_ids,
        )
        await session.commit()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"added": len(added)}


@router.post("/{kb_id}/files/remove", status_code=200)
async def remove_files_from_kb(
    kb_id: uuid.UUID,
    body: KBRemoveFilesRequest,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    svc = KBService(session)
    try:
        await svc.remove_files(
            tenant_id=tenant.id, kb_id=kb_id, file_ids=body.file_ids,
        )
        await session.commit()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"removed": len(body.file_ids)}


@router.get("/{kb_id}/articles", response_model=ArticleListResponse)
async def list_articles(
    kb_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
    category: Optional[str] = Query(None),
    article_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    # Verify KB ownership
    svc = KBService(session)
    kb = await svc.get(tenant_id=tenant.id, kb_id=kb_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    query = (
        select(Article)
        .options(selectinload(Article.sources))
        .where(Article.knowledge_base_id == kb_id)
    )
    if category is not None:
        query = query.where(Article.category == category)
    if article_type is not None:
        query = query.where(Article.article_type == article_type)
    query = query.order_by(Article.created_at.desc()).limit(limit).offset(offset)

    result = await session.execute(query)
    articles = result.scalars().all()
    responses = [ArticleResponse.model_validate(a) for a in articles]
    return ArticleListResponse(articles=responses, total=len(responses))


@router.get("/{kb_id}/articles/{article_id}", response_model=ArticleResponse)
async def get_article(
    kb_id: uuid.UUID,
    article_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    # Verify KB ownership
    svc = KBService(session)
    kb = await svc.get(tenant_id=tenant.id, kb_id=kb_id)
    if kb is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    result = await session.execute(
        select(Article)
        .options(selectinload(Article.sources))
        .where(Article.id == article_id, Article.knowledge_base_id == kb_id)
    )
    article = result.scalar_one_or_none()
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return ArticleResponse.model_validate(article)


@router.post("/{kb_id}/compile", status_code=202)
async def compile_kb_endpoint(
    kb_id: uuid.UUID,
    force: bool = False,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    svc = KBService(session)
    kb = await svc.get(tenant.id, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    asyncio.create_task(compile_kb(kb_id, tenant.id, force=force))
    return {"status": "compilation_started", "kb_id": str(kb_id)}


@router.post("/{kb_id}/search", response_model=KBSearchResponse)
async def search_kb_endpoint(
    kb_id: uuid.UUID,
    body: KBSearchRequest,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    svc = KBService(session)
    kb = await svc.get(tenant.id, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    engine = _get_engine()
    result = await engine.search_kb(
        query=body.query,
        session=session,
        tenant_id=tenant.id,
        kb_id=kb_id,
        top_k=body.top_k,
        articles_only=body.articles_only,
        content_types=body.content_types,
    )
    return KBSearchResponse(
        results=[KBSearchResultResponse(**r) for r in result["results"]],
        query_tokens=result["query_tokens"],
        search_time_ms=result["search_time_ms"],
    )
