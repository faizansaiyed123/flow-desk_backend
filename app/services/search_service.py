import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.project import Project
from app.models.task import Task

RESULT_LIMIT_PER_TYPE = 8


async def global_search(db: AsyncSession, *, tenant_id: uuid.UUID, query: str) -> list[dict]:
    if not query or len(query.strip()) < 2:
        return []
    pattern = f"%{query.lower().strip()}%"
    results: list[dict] = []

    clients = await db.execute(
        select(Client)
        .where(Client.tenant_id == tenant_id, func.lower(Client.name).like(pattern))
        .limit(RESULT_LIMIT_PER_TYPE)
    )
    for c in clients.scalars().all():
        results.append({
            "id": c.id, "type": "client", "title": c.name, "subtitle": c.company,
            "url": f"/clients/{c.id}",
        })

    projects = await db.execute(
        select(Project)
        .where(Project.tenant_id == tenant_id, func.lower(Project.name).like(pattern))
        .limit(RESULT_LIMIT_PER_TYPE)
    )
    for p in projects.scalars().all():
        results.append({
            "id": p.id, "type": "project", "title": p.name, "subtitle": p.status.value,
            "url": f"/projects/{p.id}",
        })

    tasks = await db.execute(
        select(Task)
        .where(Task.tenant_id == tenant_id, func.lower(Task.title).like(pattern))
        .limit(RESULT_LIMIT_PER_TYPE)
    )
    for t in tasks.scalars().all():
        results.append({
            "id": t.id, "type": "task", "title": t.title, "subtitle": t.status.value,
            "url": f"/projects/{t.project_id}/tasks/{t.id}",
        })

    return results
