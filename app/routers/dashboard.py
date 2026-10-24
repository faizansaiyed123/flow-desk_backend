from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import AuthContext
from app.database import get_db
from app.dependencies import get_auth_context
from app.schemas.dashboard import DashboardSummary
from app.services import dashboard_service

router = APIRouter()


@router.get("/summary", response_model=DashboardSummary)
async def get_summary(ctx: AuthContext = Depends(get_auth_context), db: AsyncSession = Depends(get_db)):
    summary = await dashboard_service.get_summary(db, tenant_id=ctx.tenant_id)
    return DashboardSummary(**summary)
