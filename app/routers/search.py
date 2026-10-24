from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import AuthContext
from app.database import get_db
from app.dependencies import get_auth_context
from app.schemas.search import SearchResultItem, SearchResults
from app.services import search_service

router = APIRouter()


@router.get("", response_model=SearchResults)
async def search(
    q: str = Query(default="", min_length=0),
    ctx: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    results = await search_service.global_search(db, tenant_id=ctx.tenant_id, query=q)
    return SearchResults(query=q, results=[SearchResultItem(**r) for r in results])
