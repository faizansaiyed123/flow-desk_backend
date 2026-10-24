import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.core.exceptions import FlowDeskError

settings = get_settings()

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("flowdesk")

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Multi-tenant project & client management platform API.",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(FlowDeskError)
async def flowdesk_error_handler(request: Request, exc: FlowDeskError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    if settings.DEBUG:
        raise exc
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


@app.get("/health", tags=["system"])
async def health_check():
    """Liveness/readiness probe for orchestrators (Docker, k8s, load balancers)."""
    return {"status": "ok", "environment": settings.ENVIRONMENT}


from app.routers import (  # noqa: E402
    auth, tenants, users, clients, projects, tasks, notifications, time_entries,
    invoices, webhooks, api_keys, attachments, activity, dashboard, search,
)

prefix = settings.API_V1_PREFIX
app.include_router(auth.router, prefix=f"{prefix}/auth", tags=["auth"])
app.include_router(tenants.router, prefix=f"{prefix}/tenants", tags=["tenants"])
app.include_router(tenants.public_router, prefix=f"{prefix}/tenants", tags=["invitations"])
app.include_router(users.router, prefix=f"{prefix}/users", tags=["users"])
app.include_router(clients.router, prefix=f"{prefix}/clients", tags=["clients"])
app.include_router(projects.router, prefix=f"{prefix}/projects", tags=["projects"])
app.include_router(tasks.router, prefix=f"{prefix}/tasks", tags=["tasks"])
app.include_router(notifications.router, prefix=f"{prefix}/notifications", tags=["notifications"])
app.include_router(time_entries.router, prefix=f"{prefix}/time-entries", tags=["time-entries"])
app.include_router(invoices.router, prefix=f"{prefix}/invoices", tags=["invoices"])
app.include_router(webhooks.router, prefix=f"{prefix}/webhooks", tags=["webhooks"])
app.include_router(api_keys.router, prefix=f"{prefix}/api-keys", tags=["api-keys"])
app.include_router(attachments.router, prefix=f"{prefix}/attachments", tags=["attachments"])
app.include_router(activity.router, prefix=f"{prefix}/activity", tags=["activity"])
app.include_router(dashboard.router, prefix=f"{prefix}/dashboard", tags=["dashboard"])
app.include_router(search.router, prefix=f"{prefix}/search", tags=["search"])
# Additional routers are included incrementally as each module is built,
# tested, and verified (see /home/claude/flowdesk/PROGRESS.md).
