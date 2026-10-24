"""Generic offset-based pagination for SQLAlchemy select statements."""
import math

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select


async def paginate(
    db: AsyncSession, stmt: Select, *, page: int = 1, page_size: int = 20
) -> tuple[list, int]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    result = await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    items = list(result.scalars().all())
    return items, total


def total_pages(total: int, page_size: int) -> int:
    return max(1, math.ceil(total / page_size))
