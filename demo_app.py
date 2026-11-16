"""Isolated, in-memory API simulator for the FlowDesk recruiter demo.

This module intentionally does not import the production app, SQLAlchemy,
Alembic, PostgreSQL, SMTP, Redis, or webhook delivery services. All state
lives in process memory and is reset when the demo server restarts.
"""
from __future__ import annotations

import base64
import json
import uuid
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import Body, Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

API_PREFIX = "/api/v1"
DEMO_PASSWORD = "Demo1234!"
TENANT_MAIN = "tenant_northstar"
TENANT_LABS = "tenant_flowdesk_labs"
TASK_STATUSES = ["backlog", "todo", "in_progress", "in_review", "done"]


def now() -> datetime:
    return datetime.now(timezone.utc)


def stamp(days: int = 0, hour: int = 10) -> str:
    value = now() + timedelta(days=days)
    return value.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


def day(days: int = 0) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def new_id(prefix: str) -> str:
    return prefix + "_" + uuid.uuid4().hex[:10]


def money(value: float) -> float:
    return round(float(value) + 1e-9, 2)


def build_seed() -> dict[str, list[dict[str, Any]]]:
    users = [
        {"id": "user_owner", "email": "alex@northstar.demo", "full_name": "Alex Morgan", "avatar_url": None, "is_email_verified": True, "is_active": True, "created_at": stamp(-180)},
        {"id": "user_admin", "email": "jordan@northstar.demo", "full_name": "Jordan Lee", "avatar_url": None, "is_email_verified": True, "is_active": True, "created_at": stamp(-120)},
        {"id": "user_member", "email": "sam@northstar.demo", "full_name": "Sam Rivera", "avatar_url": None, "is_email_verified": True, "is_active": True, "created_at": stamp(-90)},
        {"id": "user_viewer", "email": "taylor@northstar.demo", "full_name": "Taylor Chen", "avatar_url": None, "is_email_verified": True, "is_active": True, "created_at": stamp(-60)},
    ]
    tenants = [
        {"id": TENANT_MAIN, "name": "Northstar Creative", "slug": "northstar-creative", "logo_url": None, "plan": "pro", "is_active": True, "created_at": stamp(-180)},
        {"id": TENANT_LABS, "name": "FlowDesk Labs", "slug": "flowdesk-labs", "logo_url": None, "plan": "free", "is_active": True, "created_at": stamp(-28)},
    ]
    memberships = [
        {"id": "membership_owner_main", "tenant_id": TENANT_MAIN, "user_id": "user_owner", "role": "owner", "created_at": stamp(-180)},
        {"id": "membership_admin_main", "tenant_id": TENANT_MAIN, "user_id": "user_admin", "role": "admin", "created_at": stamp(-120)},
        {"id": "membership_member_main", "tenant_id": TENANT_MAIN, "user_id": "user_member", "role": "member", "created_at": stamp(-90)},
        {"id": "membership_viewer_main", "tenant_id": TENANT_MAIN, "user_id": "user_viewer", "role": "viewer", "created_at": stamp(-60)},
        {"id": "membership_owner_labs", "tenant_id": TENANT_LABS, "user_id": "user_owner", "role": "admin", "created_at": stamp(-28)},
    ]
    clients = [
        {"id": "client_aperture", "tenant_id": TENANT_MAIN, "name": "Aperture Studio", "company": "Aperture Studio LLC", "email": "hello@aperture.demo", "phone": "+1 415 555 0182", "address": "210 Market Street, San Francisco, CA", "notes": "Brand strategy and digital product client.", "is_archived": False, "created_at": stamp(-90), "updated_at": stamp(-2)},
        {"id": "client_lumen", "tenant_id": TENANT_MAIN, "name": "Lumen & Co.", "company": "Lumen & Co.", "email": "projects@lumen.demo", "phone": "+1 415 555 0144", "address": "88 Townsend Street, San Francisco, CA", "notes": "Website refresh and ongoing design support.", "is_archived": False, "created_at": stamp(-72), "updated_at": stamp(-4)},
        {"id": "client_fieldnote", "tenant_id": TENANT_MAIN, "name": "Fieldnote", "company": "Fieldnote Goods", "email": "studio@fieldnote.demo", "phone": "+1 628 555 0108", "address": "45 Valencia Street, San Francisco, CA", "notes": "Quarterly campaign retainer.", "is_archived": False, "created_at": stamp(-55), "updated_at": stamp(-3)},
        {"id": "client_arc", "tenant_id": TENANT_MAIN, "name": "Arcwell Health", "company": "Arcwell Health Inc.", "email": "ops@arcwell.demo", "phone": "+1 510 555 0133", "address": "500 3rd Street, Oakland, CA", "notes": "Mobile onboarding product work.", "is_archived": False, "created_at": stamp(-31), "updated_at": stamp(-1)},
        {"id": "client_lab", "tenant_id": TENANT_LABS, "name": "Prototype Partners", "company": "Prototype Partners", "email": "hello@prototype.demo", "phone": None, "address": "Remote", "notes": "FlowDesk Labs sample client.", "is_archived": False, "created_at": stamp(-18), "updated_at": stamp(-2)},
    ]
    projects = [
        {"id": "project_brand", "tenant_id": TENANT_MAIN, "name": "Brand identity system", "description": "Research, positioning, visual identity, and a complete brand handoff.", "status": "active", "client_id": "client_aperture", "color": "#c6963e", "billing_type": "hourly", "hourly_rate": 145, "fixed_budget": None, "start_date": day(-32), "due_date": day(12), "is_archived": False, "created_at": stamp(-32), "updated_at": stamp(-1)},
        {"id": "project_website", "tenant_id": TENANT_MAIN, "name": "Website refresh", "description": "Redesign and implementation of the Lumen marketing website.", "status": "active", "client_id": "client_lumen", "color": "#6c9bb8", "billing_type": "hourly", "hourly_rate": 125, "fixed_budget": None, "start_date": day(-18), "due_date": day(21), "is_archived": False, "created_at": stamp(-18), "updated_at": stamp(-1)},
        {"id": "project_campaign", "tenant_id": TENANT_MAIN, "name": "Quarterly campaign", "description": "Creative direction, landing page, and launch assets.", "status": "on_hold", "client_id": "client_fieldnote", "color": "#8aa783", "billing_type": "fixed", "hourly_rate": None, "fixed_budget": 12500, "start_date": day(-48), "due_date": day(8), "is_archived": False, "created_at": stamp(-48), "updated_at": stamp(-5)},
        {"id": "project_mobile", "tenant_id": TENANT_MAIN, "name": "Patient onboarding app", "description": "A mobile-first onboarding experience for Arcwell Health.", "status": "planning", "client_id": "client_arc", "color": "#a78ac4", "billing_type": "hourly", "hourly_rate": 160, "fixed_budget": None, "start_date": day(3), "due_date": day(45), "is_archived": False, "created_at": stamp(-8), "updated_at": stamp(-2)},
        {"id": "project_lab", "tenant_id": TENANT_LABS, "name": "Workspace prototype", "description": "Internal design-system and workflow prototype.", "status": "active", "client_id": "client_lab", "color": "#c6963e", "billing_type": "non_billable", "hourly_rate": None, "fixed_budget": None, "start_date": day(-10), "due_date": day(20), "is_archived": False, "created_at": stamp(-10), "updated_at": stamp(-1)},
    ]
    tasks = [
        {"id": "task_research", "tenant_id": TENANT_MAIN, "project_id": "project_brand", "title": "Complete audience interviews", "description": "Synthesize notes from five customer interviews.", "status": "done", "priority": "high", "assignee_id": "user_member", "due_date": day(-8), "position": 100, "completed_at": stamp(-7), "estimated_hours": 6, "created_at": stamp(-28), "updated_at": stamp(-7)},
        {"id": "task_moodboard", "tenant_id": TENANT_MAIN, "project_id": "project_brand", "title": "Prepare visual directions", "description": "Present three visual routes for stakeholder review.", "status": "in_review", "priority": "high", "assignee_id": "user_admin", "due_date": day(2), "position": 200, "completed_at": None, "estimated_hours": 8, "created_at": stamp(-14), "updated_at": stamp(-1)},
        {"id": "task_guidelines", "tenant_id": TENANT_MAIN, "project_id": "project_brand", "title": "Draft brand guidelines", "description": "Typography, color, spacing, imagery, and usage rules.", "status": "todo", "priority": "medium", "assignee_id": "user_member", "due_date": day(8), "position": 100, "completed_at": None, "estimated_hours": 12, "created_at": stamp(-5), "updated_at": stamp(-2)},
        {"id": "task_homepage", "tenant_id": TENANT_MAIN, "project_id": "project_website", "title": "Approve homepage wireframe", "description": "Confirm desktop and mobile page structure.", "status": "in_progress", "priority": "urgent", "assignee_id": "user_owner", "due_date": day(1), "position": 100, "completed_at": None, "estimated_hours": 5, "created_at": stamp(-12), "updated_at": stamp(0)},
        {"id": "task_copy", "tenant_id": TENANT_MAIN, "project_id": "project_website", "title": "Finalize homepage copy", "description": "Incorporate feedback into hero and product sections.", "status": "todo", "priority": "high", "assignee_id": "user_member", "due_date": day(5), "position": 200, "completed_at": None, "estimated_hours": 4, "created_at": stamp(-9), "updated_at": stamp(-2)},
        {"id": "task_campaign", "tenant_id": TENANT_MAIN, "project_id": "project_campaign", "title": "Review campaign concept", "description": "Waiting on client approval for creative direction.", "status": "todo", "priority": "medium", "assignee_id": "user_admin", "due_date": day(-2), "position": 100, "completed_at": None, "estimated_hours": 3, "created_at": stamp(-12), "updated_at": stamp(-3)},
        {"id": "task_lab", "tenant_id": TENANT_LABS, "project_id": "project_lab", "title": "Prototype command palette", "description": "Explore a global action and search palette.", "status": "in_progress", "priority": "medium", "assignee_id": "user_owner", "due_date": day(9), "position": 100, "completed_at": None, "estimated_hours": 6, "created_at": stamp(-7), "updated_at": stamp(-1)},
    ]
    times = [
        {"id": "time_1", "tenant_id": TENANT_MAIN, "project_id": "project_brand", "task_id": "task_research", "user_id": "user_member", "description": "Audience research and interview synthesis", "started_at": stamp(-6, 9), "ended_at": stamp(-6, 13), "duration_minutes": 240, "is_billable": True, "is_invoiced": False, "created_at": stamp(-6)},
        {"id": "time_2", "tenant_id": TENANT_MAIN, "project_id": "project_brand", "task_id": "task_moodboard", "user_id": "user_admin", "description": "Visual direction exploration", "started_at": stamp(-4, 10), "ended_at": stamp(-4, 13), "duration_minutes": 180, "is_billable": True, "is_invoiced": False, "created_at": stamp(-4)},
        {"id": "time_3", "tenant_id": TENANT_MAIN, "project_id": "project_website", "task_id": "task_homepage", "user_id": "user_owner", "description": "Homepage wireframe review", "started_at": stamp(-2, 9), "ended_at": stamp(-2, 12), "duration_minutes": 180, "is_billable": True, "is_invoiced": True, "created_at": stamp(-2)},
    ]

    def line(line_id: str, description: str, quantity: float, price: float, position: int = 1):
        return {"id": line_id, "description": description, "quantity": quantity, "unit_price": price, "amount": money(quantity * price), "position": position}

    invoices = [
        {"id": "invoice_paid", "tenant_id": TENANT_MAIN, "invoice_number": "INV-0008", "client_id": "client_aperture", "project_id": "project_brand", "status": "paid", "issue_date": day(-25), "due_date": day(-10), "subtotal": 870, "tax_rate": 8.5, "tax_amount": 73.95, "total": 943.95, "notes": "Brand research milestone.", "paid_at": day(-12), "line_items": [line("line_paid_1", "Brand research and discovery", 6, 145)], "created_at": stamp(-25)},
        {"id": "invoice_sent", "tenant_id": TENANT_MAIN, "invoice_number": "INV-0009", "client_id": "client_lumen", "project_id": "project_website", "status": "sent", "issue_date": day(-8), "due_date": day(22), "subtotal": 625, "tax_rate": 8.5, "tax_amount": 53.13, "total": 678.13, "notes": "Homepage wireframe milestone.", "paid_at": None, "line_items": [line("line_sent_1", "UX and homepage wireframes", 5, 125)], "created_at": stamp(-8)},
        {"id": "invoice_overdue", "tenant_id": TENANT_MAIN, "invoice_number": "INV-0010", "client_id": "client_fieldnote", "project_id": "project_campaign", "status": "overdue", "issue_date": day(-35), "due_date": day(-5), "subtotal": 1200, "tax_rate": 8.5, "tax_amount": 102, "total": 1302, "notes": "Monthly creative retainer.", "paid_at": None, "line_items": [line("line_overdue_1", "Campaign creative retainer", 1, 1200)], "created_at": stamp(-35)},
        {"id": "invoice_draft", "tenant_id": TENANT_MAIN, "invoice_number": "INV-0011", "client_id": "client_aperture", "project_id": "project_brand", "status": "draft", "issue_date": day(0), "due_date": day(30), "subtotal": 0, "tax_rate": 8.5, "tax_amount": 0, "total": 0, "notes": "Draft prepared from unbilled time.", "paid_at": None, "line_items": [], "created_at": stamp(-1)},
    ]
    return {
        "tenants": tenants, "users": users, "memberships": memberships, "clients": clients,
        "projects": projects, "tasks": tasks, "timeEntries": times, "invoices": invoices,
        "comments": [
            {"id": "comment_1", "tenant_id": TENANT_MAIN, "task_id": "task_moodboard", "author_id": "user_admin", "body": "First direction is ready for a quick review.", "created_at": stamp(-1)},
            {"id": "comment_2", "tenant_id": TENANT_MAIN, "task_id": "task_moodboard", "author_id": "user_owner", "body": "The warmer palette is closest to the brief. Please refine that route.", "created_at": stamp(0)},
        ],
        "notifications": [
            {"id": "notification_1", "tenant_id": TENANT_MAIN, "type": "task.assigned", "title": "A task is waiting for review", "body": "Visual directions are ready for your feedback.", "link": "/app/projects/project_brand", "is_read": False, "created_at": stamp(-1)},
            {"id": "notification_2", "tenant_id": TENANT_MAIN, "type": "invoice.overdue", "title": "Invoice INV-0010 is overdue", "body": "Fieldnote has an outstanding invoice of $1,302.00.", "link": "/app/invoices/invoice_overdue", "is_read": False, "created_at": stamp(-1)},
        ],
        "activity": [
            {"id": "activity_1", "tenant_id": TENANT_MAIN, "actor_id": "user_member", "action": "task.completed", "entity_type": "task", "entity_id": "task_research", "entity_label": "Complete audience interviews", "metadata_json": None, "created_at": stamp(-1)},
            {"id": "activity_2", "tenant_id": TENANT_MAIN, "actor_id": "user_admin", "action": "comment.created", "entity_type": "task", "entity_id": "task_moodboard", "entity_label": "Visual directions", "metadata_json": None, "created_at": stamp(-1)},
        ],
        "invitations": [{"id": "invite_pending", "tenant_id": TENANT_MAIN, "email": "new.collaborator@northstar.demo", "role": "member", "status": "pending", "expires_at": stamp(6), "created_at": stamp(-1)}],
        "apiKeys": [{"id": "key_1", "tenant_id": TENANT_MAIN, "name": "Local reporting integration", "key_prefix": "fd_demo_8a3", "is_active": True, "last_used_at": stamp(-2), "created_at": stamp(-30)}],
        "webhooks": [{"id": "webhook_1", "tenant_id": TENANT_MAIN, "target_url": "https://example.test/flowdesk-events", "events": ["task.completed", "invoice.paid"], "description": "Sample analytics integration", "is_active": True, "created_at": stamp(-15)}],
        "webhookDeliveries": [{"id": "delivery_1", "tenant_id": TENANT_MAIN, "webhook_id": "webhook_1", "event": "task.completed", "response_status": 200, "success": True, "attempted_at": stamp(-1)}],
        "attachments": [{"id": "attachment_1", "tenant_id": TENANT_MAIN, "project_id": "project_brand", "task_id": None, "uploaded_by_id": "user_owner", "file_name": "brand-discovery-brief.pdf", "content_type": "application/pdf", "size_bytes": 284100, "created_at": stamp(-8)}],
    }


STATE = build_seed()


def reset_demo_state() -> None:
    global STATE
    STATE = build_seed()


def issue_tokens(user_id: str, tenant_id: str) -> dict[str, str]:
    payload = base64.b64encode(json.dumps({"sub": user_id, "tenant_id": tenant_id}).encode()).decode()
    return {
        "access_token": "demo." + payload + ".local",
        "refresh_token": "demo-refresh." + payload + ".local",
        "token_type": "bearer",
    }


def filtered(key: str, tenant_id: str) -> list[dict[str, Any]]:
    return [item for item in STATE[key] if item.get("tenant_id") == tenant_id]


def paginate(items: list[dict[str, Any]], page: int = 1, page_size: int = 20) -> dict[str, Any]:
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    start = (page - 1) * page_size
    return {"items": items[start:start + page_size], "total": len(items), "page": page, "page_size": page_size, "total_pages": (len(items) + page_size - 1) // page_size}


def current_context(request: Request) -> dict[str, Any]:
    header = request.headers.get("authorization", "")
    token = header.removeprefix("Bearer ").strip()
    try:
        payload = token.split(".")[1]
        decoded = base64.b64decode(payload + "=" * (-len(payload) % 4))
        claims = json.loads(decoded)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Not authenticated.") from exc
    user = next((item for item in STATE["users"] if item["id"] == claims.get("sub")), None)
    tenant_id = claims.get("tenant_id")
    membership = next((item for item in STATE["memberships"] if item["user_id"] == (user or {}).get("id") and item["tenant_id"] == tenant_id), None)
    if not user or not user.get("is_active", True) or not membership:
        raise HTTPException(status_code=401, detail="Session expired or workspace membership not found.")
    return {"user": user, "tenant_id": tenant_id, "membership": membership, "role": membership["role"]}


def require_role(ctx: dict[str, Any], allowed: tuple[str, ...]) -> None:
    if ctx["role"] not in allowed:
        raise HTTPException(status_code=403, detail="Your workspace role does not allow this action.")


def add_activity(ctx: dict[str, Any], action: str, entity_type: str, entity_id: str, label: str) -> None:
    STATE["activity"].insert(0, {
        "id": new_id("activity"), "tenant_id": ctx["tenant_id"], "actor_id": ctx["user"]["id"],
        "action": action, "entity_type": entity_type, "entity_id": entity_id, "entity_label": label,
        "metadata_json": None, "created_at": now().isoformat(),
    })


def project_stats(project: dict[str, Any]) -> dict[str, Any]:
    tasks = [item for item in filtered("tasks", project["tenant_id"]) if item["project_id"] == project["id"]]
    entries = [item for item in filtered("timeEntries", project["tenant_id"]) if item["project_id"] == project["id"]]
    client = next((item for item in filtered("clients", project["tenant_id"]) if item["id"] == project.get("client_id")), None)
    minutes = sum(item.get("duration_minutes") or 0 for item in entries)
    billable = sum((item.get("duration_minutes") or 0) / 60 * (project.get("hourly_rate") or 0) for item in entries if item.get("is_billable"))
    return {
        **project, "client_name": client["name"] if client else None, "task_count": len(tasks),
        "completed_task_count": sum(item["status"] == "done" for item in tasks),
        "total_hours_logged": round(minutes / 60, 2), "total_billable_amount": money(billable),
    }


def client_stats(client: dict[str, Any]) -> dict[str, Any]:
    projects = [item for item in filtered("projects", client["tenant_id"]) if item.get("client_id") == client["id"]]
    invoices = [item for item in filtered("invoices", client["tenant_id"]) if item.get("client_id") == client["id"]]
    return {
        **client, "project_count": len(projects), "active_project_count": sum(item["status"] == "active" for item in projects),
        "total_invoiced": money(sum(item["total"] for item in invoices)),
        "total_outstanding": money(sum(item["total"] for item in invoices if item["status"] in ("sent", "overdue"))),
    }


def add_invoice(ctx: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    lines = []
    for index, item in enumerate(payload.get("line_items", []), 1):
        quantity = float(item.get("quantity", 1))
        unit_price = float(item.get("unit_price", 0))
        lines.append({"id": new_id("line"), "description": item["description"], "quantity": quantity, "unit_price": unit_price, "amount": money(quantity * unit_price), "position": index})
    subtotal = money(sum(item["amount"] for item in lines))
    tax_rate = float(payload.get("tax_rate") or 0)
    tax_amount = money(subtotal * tax_rate / 100)
    invoices = filtered("invoices", ctx["tenant_id"])
    invoice = {
        "id": new_id("invoice"), "tenant_id": ctx["tenant_id"], "invoice_number": "INV-" + str(12 + len(invoices)).zfill(4),
        "client_id": payload["client_id"], "project_id": payload.get("project_id"), "status": "draft",
        "issue_date": payload.get("issue_date", day()), "due_date": payload.get("due_date", day(30)),
        "subtotal": subtotal, "tax_rate": tax_rate, "tax_amount": tax_amount, "total": money(subtotal + tax_amount),
        "notes": payload.get("notes"), "paid_at": None, "line_items": lines, "created_at": now().isoformat(),
    }
    STATE["invoices"].append(invoice)
    add_activity(ctx, "invoice.created", "invoice", invoice["id"], invoice["invoice_number"])
    return invoice


app = FastAPI(
    title="FlowDesk Demo API",
    version="1.0.0-demo",
    description="In-memory recruiter simulation. Not the production FlowDesk backend.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "environment": "in-memory-demo"}


@app.post(API_PREFIX + "/auth/login")
async def login(payload: dict[str, Any] = Body(...)):
    email = str(payload.get("email", "")).lower()
    user = next((item for item in STATE["users"] if item["email"].lower() == email), None)
    if not user or payload.get("password") != DEMO_PASSWORD:
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    membership = next((item for item in STATE["memberships"] if item["user_id"] == user["id"]), None)
    if not membership:
        raise HTTPException(status_code=401, detail="This account has no demo workspace.")
    requested_tenant = payload.get("tenant_id")
    if requested_tenant:
        membership = next((item for item in STATE["memberships"] if item["user_id"] == user["id"] and item["tenant_id"] == requested_tenant), None)
        if not membership:
            raise HTTPException(status_code=401, detail="You are not a member of that workspace.")
    return issue_tokens(user["id"], membership["tenant_id"])


@app.post(API_PREFIX + "/auth/register")
async def register(payload: dict[str, Any] = Body(...)):
    email = str(payload.get("email", "")).lower()
    if any(item["email"].lower() == email for item in STATE["users"]):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = {"id": new_id("user"), "email": email, "full_name": payload.get("full_name", "New User"), "avatar_url": None, "is_email_verified": True, "is_active": True, "created_at": now().isoformat()}
    tenant = {"id": new_id("tenant"), "name": payload.get("workspace_name", "My Workspace"), "slug": new_id("workspace"), "logo_url": None, "plan": "free", "is_active": True, "created_at": now().isoformat()}
    membership = {"id": new_id("membership"), "tenant_id": tenant["id"], "user_id": user["id"], "role": "owner", "created_at": now().isoformat()}
    STATE["users"].append(user)
    STATE["tenants"].append(tenant)
    STATE["memberships"].append(membership)
    return issue_tokens(user["id"], tenant["id"])


@app.post(API_PREFIX + "/auth/refresh")
async def refresh(ctx: dict[str, Any] = Depends(current_context)):
    return issue_tokens(ctx["user"]["id"], ctx["tenant_id"])


@app.post(API_PREFIX + "/auth/switch-tenant")
async def switch_tenant(payload: dict[str, Any] = Body(...), ctx: dict[str, Any] = Depends(current_context)):
    membership = next((item for item in STATE["memberships"] if item["user_id"] == ctx["user"]["id"] and item["tenant_id"] == payload.get("tenant_id")), None)
    if not membership:
        raise HTTPException(status_code=403, detail="You are not a member of that workspace.")
    return issue_tokens(ctx["user"]["id"], membership["tenant_id"])


@app.get(API_PREFIX + "/auth/me")
async def me(ctx: dict[str, Any] = Depends(current_context)):
    memberships = []
    for membership in STATE["memberships"]:
        if membership["user_id"] == ctx["user"]["id"]:
            memberships.append({"id": membership["id"], "role": membership["role"], "tenant_id": membership["tenant_id"], "user": deepcopy(ctx["user"])})
    return {"user": ctx["user"], "memberships": memberships}


@app.post(API_PREFIX + "/auth/forgot-password")
async def forgot_password(payload: dict[str, Any] = Body(...)):
    return {"message": "If the account exists, a password-reset link would be sent. Email delivery is disabled in the demo.", "simulated": True}


@app.patch(API_PREFIX + "/users/me")
async def update_profile(payload: dict[str, Any] = Body(...), ctx: dict[str, Any] = Depends(current_context)):
    ctx["user"].update(payload)
    return ctx["user"]


@app.get(API_PREFIX + "/tenants/current")
async def current_tenant(ctx: dict[str, Any] = Depends(current_context)):
    return next(item for item in STATE["tenants"] if item["id"] == ctx["tenant_id"])


@app.patch(API_PREFIX + "/tenants/current")
async def update_tenant(payload: dict[str, Any] = Body(...), ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin"))
    tenant = next(item for item in STATE["tenants"] if item["id"] == ctx["tenant_id"])
    tenant.update(payload)
    return tenant


@app.get(API_PREFIX + "/tenants/members")
async def members(ctx: dict[str, Any] = Depends(current_context)):
    return [
        {"membership_id": membership["id"], "user": next(item for item in STATE["users"] if item["id"] == membership["user_id"]), "role": membership["role"], "joined_at": membership["created_at"]}
        for membership in filtered("memberships", ctx["tenant_id"])
    ]


@app.patch(API_PREFIX + "/tenants/members/{membership_id}/role")
async def member_role(membership_id: str, payload: dict[str, Any] = Body(...), ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin"))
    membership = next((item for item in filtered("memberships", ctx["tenant_id"]) if item["id"] == membership_id), None)
    if not membership or membership["role"] == "owner":
        raise HTTPException(status_code=404, detail="Workspace member not found.")
    membership["role"] = payload["role"]
    return {"message": "Role updated."}


@app.delete(API_PREFIX + "/tenants/members/{membership_id}")
async def remove_member(membership_id: str, ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin"))
    STATE["memberships"] = [item for item in STATE["memberships"] if not (item["id"] == membership_id and item["tenant_id"] == ctx["tenant_id"])]
    return {"message": "Member removed."}


@app.get(API_PREFIX + "/tenants/invitations")
async def list_invitations(ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin"))
    return filtered("invitations", ctx["tenant_id"])


@app.post(API_PREFIX + "/tenants/invitations", status_code=201)
async def create_invitation(payload: dict[str, Any] = Body(...), ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin"))
    invitation = {"id": new_id("invite"), "tenant_id": ctx["tenant_id"], "email": payload["email"], "role": payload.get("role", "member"), "status": "pending", "expires_at": stamp(7), "created_at": now().isoformat()}
    STATE["invitations"].append(invitation)
    add_activity(ctx, "invitation.created", "invitation", invitation["id"], invitation["email"])
    return invitation


@app.delete(API_PREFIX + "/tenants/invitations/{invitation_id}")
async def revoke_invitation(invitation_id: str, ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin"))
    invite = next((item for item in filtered("invitations", ctx["tenant_id"]) if item["id"] == invitation_id), None)
    if invite:
        invite["status"] = "revoked"
    return {"message": "Invitation revoked."}


@app.get(API_PREFIX + "/clients")
async def list_clients(search: str | None = None, include_archived: bool = False, page: int = 1, page_size: int = 20, ctx: dict[str, Any] = Depends(current_context)):
    items = filtered("clients", ctx["tenant_id"])
    if not include_archived:
        items = [item for item in items if not item["is_archived"]]
    if search:
        items = [item for item in items if search.lower() in " ".join(str(item.get(key) or "") for key in ("name", "company", "email")).lower()]
    return paginate(items, page, page_size)


@app.post(API_PREFIX + "/clients", status_code=201)
async def create_client(payload: dict[str, Any] = Body(...), ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin", "member"))
    client = {"id": new_id("client"), "tenant_id": ctx["tenant_id"], "name": payload["name"], "company": payload.get("company"), "email": payload.get("email"), "phone": payload.get("phone"), "address": payload.get("address"), "notes": payload.get("notes"), "is_archived": False, "created_at": now().isoformat(), "updated_at": now().isoformat()}
    STATE["clients"].append(client)
    add_activity(ctx, "client.created", "client", client["id"], client["name"])
    return client


@app.get(API_PREFIX + "/clients/{client_id}")
async def get_client(client_id: str, ctx: dict[str, Any] = Depends(current_context)):
    client = next((item for item in filtered("clients", ctx["tenant_id"]) if item["id"] == client_id), None)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")
    return client_stats(client)


@app.patch(API_PREFIX + "/clients/{client_id}")
async def update_client(client_id: str, payload: dict[str, Any] = Body(...), ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin", "member"))
    client = next((item for item in filtered("clients", ctx["tenant_id"]) if item["id"] == client_id), None)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")
    client.update(payload)
    client["updated_at"] = now().isoformat()
    return client


@app.post(API_PREFIX + "/clients/{client_id}/archive")
async def archive_client(client_id: str, ctx: dict[str, Any] = Depends(current_context)):
    client = next((item for item in filtered("clients", ctx["tenant_id"]) if item["id"] == client_id), None)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")
    client["is_archived"] = True
    return client


@app.delete(API_PREFIX + "/clients/{client_id}")
async def delete_client(client_id: str, ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin"))
    before = len(STATE["clients"])
    STATE["clients"] = [item for item in STATE["clients"] if not (item["id"] == client_id and item["tenant_id"] == ctx["tenant_id"])]
    if len(STATE["clients"]) == before:
        raise HTTPException(status_code=404, detail="Client not found.")
    return {"message": "Client deleted."}


@app.get(API_PREFIX + "/projects")
async def list_projects(search: str | None = None, status: str | None = None, client_id: str | None = None, include_archived: bool = False, page: int = 1, page_size: int = 20, ctx: dict[str, Any] = Depends(current_context)):
    items = filtered("projects", ctx["tenant_id"])
    if not include_archived:
        items = [item for item in items if not item["is_archived"]]
    if search:
        items = [item for item in items if search.lower() in item["name"].lower()]
    if status:
        items = [item for item in items if item["status"] == status]
    if client_id:
        items = [item for item in items if item.get("client_id") == client_id]
    return paginate([project_stats(item) for item in items], page, page_size)


@app.post(API_PREFIX + "/projects", status_code=201)
async def create_project(payload: dict[str, Any] = Body(...), ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin", "member"))
    project = {"id": new_id("project"), "tenant_id": ctx["tenant_id"], "name": payload["name"], "description": payload.get("description"), "status": payload.get("status", "planning"), "client_id": payload.get("client_id"), "color": payload.get("color", "#c6963e"), "billing_type": payload.get("billing_type", "hourly"), "hourly_rate": payload.get("hourly_rate"), "fixed_budget": payload.get("fixed_budget"), "start_date": payload.get("start_date"), "due_date": payload.get("due_date"), "is_archived": False, "created_at": now().isoformat(), "updated_at": now().isoformat()}
    if project["client_id"] and not any(item["id"] == project["client_id"] for item in filtered("clients", ctx["tenant_id"])):
        raise HTTPException(status_code=422, detail="Client is not in this workspace.")
    STATE["projects"].append(project)
    add_activity(ctx, "project.created", "project", project["id"], project["name"])
    return project


@app.get(API_PREFIX + "/projects/{project_id}")
async def get_project(project_id: str, ctx: dict[str, Any] = Depends(current_context)):
    project = next((item for item in filtered("projects", ctx["tenant_id"]) if item["id"] == project_id), None)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project_stats(project)


@app.patch(API_PREFIX + "/projects/{project_id}")
async def update_project(project_id: str, payload: dict[str, Any] = Body(...), ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin", "member"))
    project = next((item for item in filtered("projects", ctx["tenant_id"]) if item["id"] == project_id), None)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    project.update(payload)
    project["updated_at"] = now().isoformat()
    return project


@app.delete(API_PREFIX + "/projects/{project_id}")
async def delete_project(project_id: str, ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin"))
    project = next((item for item in filtered("projects", ctx["tenant_id"]) if item["id"] == project_id), None)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    STATE["projects"] = [item for item in STATE["projects"] if item["id"] != project_id]
    STATE["tasks"] = [item for item in STATE["tasks"] if item["project_id"] != project_id]
    return {"message": "Project deleted."}


@app.get(API_PREFIX + "/tasks/board/{project_id}")
async def task_board(project_id: str, ctx: dict[str, Any] = Depends(current_context)):
    if not any(item["id"] == project_id for item in filtered("projects", ctx["tenant_id"])):
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"columns": [{"status": status, "tasks": sorted([item for item in filtered("tasks", ctx["tenant_id"]) if item["project_id"] == project_id and item["status"] == status], key=lambda item: item["position"])} for status in TASK_STATUSES]}


@app.get(API_PREFIX + "/tasks")
async def list_tasks(project_id: str | None = None, status: str | None = None, assignee_id: str | None = None, search: str | None = None, page: int = 1, page_size: int = 50, ctx: dict[str, Any] = Depends(current_context)):
    items = filtered("tasks", ctx["tenant_id"])
    if project_id: items = [item for item in items if item["project_id"] == project_id]
    if status: items = [item for item in items if item["status"] == status]
    if assignee_id: items = [item for item in items if item.get("assignee_id") == assignee_id]
    if search: items = [item for item in items if search.lower() in item["title"].lower()]
    return paginate(items, page, page_size)


@app.post(API_PREFIX + "/tasks", status_code=201)
async def create_task(payload: dict[str, Any] = Body(...), ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin", "member"))
    if not any(item["id"] == payload["project_id"] for item in filtered("projects", ctx["tenant_id"])):
        raise HTTPException(status_code=422, detail="Project is not in this workspace.")
    sibling_positions = [item["position"] for item in filtered("tasks", ctx["tenant_id"]) if item["project_id"] == payload["project_id"] and item["status"] == payload.get("status", "todo")]
    task = {"id": new_id("task"), "tenant_id": ctx["tenant_id"], "project_id": payload["project_id"], "title": payload["title"], "description": payload.get("description"), "status": payload.get("status", "todo"), "priority": payload.get("priority", "medium"), "assignee_id": payload.get("assignee_id"), "due_date": payload.get("due_date"), "position": max(sibling_positions, default=0) + 100, "completed_at": None, "estimated_hours": payload.get("estimated_hours"), "created_at": now().isoformat(), "updated_at": now().isoformat()}
    STATE["tasks"].append(task)
    add_activity(ctx, "task.created", "task", task["id"], task["title"])
    return task


@app.get(API_PREFIX + "/tasks/{task_id}/comments")
async def list_comments(task_id: str, ctx: dict[str, Any] = Depends(current_context)):
    return [item for item in filtered("comments", ctx["tenant_id"]) if item["task_id"] == task_id]


@app.post(API_PREFIX + "/tasks/{task_id}/comments", status_code=201)
async def add_comment(task_id: str, payload: dict[str, Any] = Body(...), ctx: dict[str, Any] = Depends(current_context)):
    task = next((item for item in filtered("tasks", ctx["tenant_id"]) if item["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    comment = {"id": new_id("comment"), "tenant_id": ctx["tenant_id"], "task_id": task_id, "author_id": ctx["user"]["id"], "body": payload["body"], "created_at": now().isoformat()}
    STATE["comments"].append(comment)
    return comment


@app.patch(API_PREFIX + "/tasks/{task_id}/move")
async def move_task(task_id: str, payload: dict[str, Any] = Body(...), ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin", "member"))
    task = next((item for item in filtered("tasks", ctx["tenant_id"]) if item["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    task["status"] = payload["status"]
    task["position"] = float(payload["position"])
    task["completed_at"] = now().isoformat() if task["status"] == "done" else None
    task["updated_at"] = now().isoformat()
    add_activity(ctx, "task.moved", "task", task["id"], task["title"])
    return task


@app.get(API_PREFIX + "/tasks/{task_id}")
async def get_task(task_id: str, ctx: dict[str, Any] = Depends(current_context)):
    task = next((item for item in filtered("tasks", ctx["tenant_id"]) if item["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@app.patch(API_PREFIX + "/tasks/{task_id}")
async def update_task(task_id: str, payload: dict[str, Any] = Body(...), ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin", "member"))
    task = next((item for item in filtered("tasks", ctx["tenant_id"]) if item["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    task.update(payload)
    task["updated_at"] = now().isoformat()
    if task["status"] == "done" and not task.get("completed_at"):
        task["completed_at"] = task["updated_at"]
    if task["status"] != "done":
        task["completed_at"] = None
    return task


@app.delete(API_PREFIX + "/tasks/{task_id}")
async def delete_task(task_id: str, ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin", "member"))
    before = len(STATE["tasks"])
    STATE["tasks"] = [item for item in STATE["tasks"] if not (item["id"] == task_id and item["tenant_id"] == ctx["tenant_id"])]
    STATE["comments"] = [item for item in STATE["comments"] if not (item["task_id"] == task_id and item["tenant_id"] == ctx["tenant_id"])]
    if before == len(STATE["tasks"]):
        raise HTTPException(status_code=404, detail="Task not found.")
    return {"message": "Task deleted."}


@app.get(API_PREFIX + "/time-entries/timer/running")
async def running_timer(ctx: dict[str, Any] = Depends(current_context)):
    return next((item for item in filtered("timeEntries", ctx["tenant_id"]) if item["user_id"] == ctx["user"]["id"] and not item.get("ended_at")), None)


@app.post(API_PREFIX + "/time-entries/timer/start", status_code=201)
async def start_timer(payload: dict[str, Any] = Body(...), ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin", "member"))
    if awaitable_running := next((item for item in filtered("timeEntries", ctx["tenant_id"]) if item["user_id"] == ctx["user"]["id"] and not item.get("ended_at")), None):
        raise HTTPException(status_code=409, detail="A timer is already running.")
    entry = {"id": new_id("time"), "tenant_id": ctx["tenant_id"], "project_id": payload["project_id"], "task_id": payload.get("task_id"), "user_id": ctx["user"]["id"], "description": payload.get("description"), "started_at": now().isoformat(), "ended_at": None, "duration_minutes": None, "is_billable": True, "is_invoiced": False, "created_at": now().isoformat()}
    STATE["timeEntries"].append(entry)
    return entry


@app.post(API_PREFIX + "/time-entries/timer/stop")
async def stop_timer(ctx: dict[str, Any] = Depends(current_context)):
    entry = next((item for item in filtered("timeEntries", ctx["tenant_id"]) if item["user_id"] == ctx["user"]["id"] and not item.get("ended_at")), None)
    if not entry:
        raise HTTPException(status_code=404, detail="No running timer was found.")
    entry["ended_at"] = now().isoformat()
    entry["duration_minutes"] = max(1, int((datetime.fromisoformat(entry["ended_at"]) - datetime.fromisoformat(entry["started_at"])).total_seconds() // 60))
    return entry


@app.get(API_PREFIX + "/time-entries")
async def list_time_entries(project_id: str | None = None, user_id: str | None = None, is_invoiced: bool | None = None, page: int = 1, page_size: int = 50, ctx: dict[str, Any] = Depends(current_context)):
    items = filtered("timeEntries", ctx["tenant_id"])
    if project_id: items = [item for item in items if item["project_id"] == project_id]
    if user_id: items = [item for item in items if item["user_id"] == user_id]
    if is_invoiced is not None: items = [item for item in items if item["is_invoiced"] == is_invoiced]
    return paginate(items, page, page_size)


@app.post(API_PREFIX + "/time-entries", status_code=201)
async def create_time_entry(payload: dict[str, Any] = Body(...), ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin", "member"))
    started = payload.get("started_at", now().isoformat())
    ended = payload.get("ended_at")
    duration = payload.get("duration_minutes")
    if not ended and duration is None:
        raise HTTPException(status_code=422, detail="Provide an end time or duration.")
    if duration is None and ended:
        duration = max(1, int((datetime.fromisoformat(ended.replace("Z", "+00:00")) - datetime.fromisoformat(started.replace("Z", "+00:00"))).total_seconds() // 60))
    entry = {"id": new_id("time"), "tenant_id": ctx["tenant_id"], "project_id": payload["project_id"], "task_id": payload.get("task_id"), "user_id": ctx["user"]["id"], "description": payload.get("description"), "started_at": started, "ended_at": ended, "duration_minutes": duration, "is_billable": payload.get("is_billable", True), "is_invoiced": False, "created_at": now().isoformat()}
    STATE["timeEntries"].append(entry)
    add_activity(ctx, "time.logged", "time_entry", entry["id"], entry.get("description") or "Time entry")
    return entry


@app.patch(API_PREFIX + "/time-entries/{entry_id}")
async def update_time_entry(entry_id: str, payload: dict[str, Any] = Body(...), ctx: dict[str, Any] = Depends(current_context)):
    entry = next((item for item in filtered("timeEntries", ctx["tenant_id"]) if item["id"] == entry_id), None)
    if not entry or entry["is_invoiced"]:
        raise HTTPException(status_code=404, detail="Time entry not found or already invoiced.")
    entry.update(payload)
    if entry.get("ended_at"):
        start = datetime.fromisoformat(entry["started_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(entry["ended_at"].replace("Z", "+00:00"))
        entry["duration_minutes"] = max(1, int((end - start).total_seconds() // 60))
    return entry


@app.delete(API_PREFIX + "/time-entries/{entry_id}")
async def delete_time_entry(entry_id: str, ctx: dict[str, Any] = Depends(current_context)):
    entry = next((item for item in filtered("timeEntries", ctx["tenant_id"]) if item["id"] == entry_id), None)
    if not entry or entry["is_invoiced"]:
        raise HTTPException(status_code=404, detail="Time entry not found or already invoiced.")
    STATE["timeEntries"] = [item for item in STATE["timeEntries"] if item["id"] != entry_id]
    return {"message": "Time entry deleted."}


@app.get(API_PREFIX + "/invoices")
async def list_invoices(status: str | None = None, client_id: str | None = None, page: int = 1, page_size: int = 50, ctx: dict[str, Any] = Depends(current_context)):
    items = filtered("invoices", ctx["tenant_id"])
    if status: items = [item for item in items if item["status"] == status]
    if client_id: items = [item for item in items if item["client_id"] == client_id]
    return paginate(items, page, page_size)


@app.post(API_PREFIX + "/invoices", status_code=201)
async def create_invoice(payload: dict[str, Any] = Body(...), ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin"))
    if not any(item["id"] == payload["client_id"] for item in filtered("clients", ctx["tenant_id"])):
        raise HTTPException(status_code=422, detail="Client is not in this workspace.")
    return add_invoice(ctx, payload)


@app.post(API_PREFIX + "/invoices/generate-from-time", status_code=201)
async def generate_invoice_from_time(payload: dict[str, Any] = Body(...), ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin"))
    project = next((item for item in filtered("projects", ctx["tenant_id"]) if item["id"] == payload["project_id"]), None)
    if not project or project["billing_type"] != "hourly" or not project.get("hourly_rate"):
        raise HTTPException(status_code=422, detail="Set an hourly rate before generating an invoice.")
    entries = [item for item in filtered("timeEntries", ctx["tenant_id"]) if item["project_id"] == project["id"] and item["is_billable"] and not item["is_invoiced"] and item.get("ended_at")]
    if not entries:
        raise HTTPException(status_code=422, detail="There is no unbilled time for this project.")
    minutes = sum(item["duration_minutes"] or 0 for item in entries)
    invoice = add_invoice(ctx, {
        "client_id": project["client_id"], "project_id": project["id"],
        "issue_date": payload.get("issue_date", day()), "due_date": payload.get("due_date", day(30)),
        "tax_rate": payload.get("tax_rate", 0), "notes": payload.get("notes", "Generated from project time."),
        "line_items": [{"description": "Project time (" + f"{minutes / 60:.2f}" + " hours)", "quantity": round(minutes / 60, 2), "unit_price": project["hourly_rate"]}],
    })
    for entry in entries:
        entry["is_invoiced"] = True
    return invoice


@app.get(API_PREFIX + "/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, ctx: dict[str, Any] = Depends(current_context)):
    invoice = next((item for item in filtered("invoices", ctx["tenant_id"]) if item["id"] == invoice_id), None)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    return invoice


@app.patch(API_PREFIX + "/invoices/{invoice_id}")
async def update_invoice(invoice_id: str, payload: dict[str, Any] = Body(...), ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin"))
    invoice = next((item for item in filtered("invoices", ctx["tenant_id"]) if item["id"] == invoice_id), None)
    if not invoice or invoice["status"] != "draft":
        raise HTTPException(status_code=422, detail="Only draft invoices can be updated.")
    invoice.update(payload)
    if "line_items" in payload:
        invoice["line_items"] = [{"id": new_id("line"), "description": item["description"], "quantity": float(item["quantity"]), "unit_price": float(item["unit_price"]), "amount": money(float(item["quantity"]) * float(item["unit_price"])), "position": index + 1} for index, item in enumerate(payload["line_items"])]
    invoice["subtotal"] = money(sum(item["amount"] for item in invoice["line_items"]))
    invoice["tax_amount"] = money(invoice["subtotal"] * invoice["tax_rate"] / 100)
    invoice["total"] = money(invoice["subtotal"] + invoice["tax_amount"])
    return invoice


@app.post(API_PREFIX + "/invoices/{invoice_id}/{action}")
async def invoice_action(invoice_id: str, action: str, ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin"))
    invoice = next((item for item in filtered("invoices", ctx["tenant_id"]) if item["id"] == invoice_id), None)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    transitions = {"send": ("draft", "sent"), "mark-paid": ("sent", "paid"), "mark-overdue": ("sent", "overdue"), "void": (("draft", "sent", "overdue"), "void")}
    if action not in transitions:
        raise HTTPException(status_code=404, detail="Unknown invoice action.")
    allowed, next_status = transitions[action]
    allowed_statuses = allowed if isinstance(allowed, tuple) else (allowed,)
    if invoice["status"] not in allowed_statuses:
        raise HTTPException(status_code=422, detail="This invoice cannot make that status transition.")
    invoice["status"] = next_status
    if next_status == "paid":
        invoice["paid_at"] = day()
    add_activity(ctx, "invoice." + next_status, "invoice", invoice["id"], invoice["invoice_number"])
    return invoice


@app.delete(API_PREFIX + "/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str, ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin"))
    invoice = next((item for item in filtered("invoices", ctx["tenant_id"]) if item["id"] == invoice_id), None)
    if not invoice or invoice["status"] != "draft":
        raise HTTPException(status_code=422, detail="Only draft invoices can be deleted.")
    STATE["invoices"] = [item for item in STATE["invoices"] if item["id"] != invoice_id]
    return {"message": "Invoice deleted."}


@app.get(API_PREFIX + "/dashboard/summary")
async def dashboard_summary(ctx: dict[str, Any] = Depends(current_context)):
    projects = [item for item in filtered("projects", ctx["tenant_id"]) if not item["is_archived"]]
    clients = [item for item in filtered("clients", ctx["tenant_id"]) if not item["is_archived"]]
    tasks = filtered("tasks", ctx["tenant_id"])
    entries = filtered("timeEntries", ctx["tenant_id"])
    invoices = filtered("invoices", ctx["tenant_id"])
    overdue = [item for item in tasks if item["status"] != "done" and item.get("due_date") and item["due_date"] < day()]
    recent_entries = [item for item in entries if item["started_at"] >= stamp(-7)]
    health = []
    for project in projects:
        stats = project_stats(project)
        health.append({"id": project["id"], "name": project["name"], "color": project["color"], "status": project["status"], "task_count": stats["task_count"], "completed_task_count": stats["completed_task_count"], "percent_complete": round(stats["completed_task_count"] * 100 / stats["task_count"]) if stats["task_count"] else 0, "due_date": project.get("due_date")})
    upcoming = []
    for task in sorted([item for item in tasks if item["status"] != "done" and item.get("due_date")], key=lambda item: item["due_date"])[:6]:
        project = next((item for item in projects if item["id"] == task["project_id"]), None)
        upcoming.append({"id": task["id"], "title": task["title"], "project_id": task["project_id"], "project_name": project["name"] if project else "Project", "due_date": task["due_date"], "priority": task["priority"]})
    revenue = [{"month": label, "invoiced": invoiced, "collected": collected} for label, invoiced, collected in zip(["Jun", "Jul", "Aug", "Sep", "Oct", "Nov"], [3200, 4600, 3900, 5400, 6100, 7200], [2900, 4100, 3600, 4900, 5700, 6400])]
    return {
        "active_project_count": sum(item["status"] == "active" for item in projects), "total_client_count": len(clients),
        "total_task_count": len(tasks), "overdue_task_count": len(overdue),
        "completed_tasks_last_7_days": sum(item["status"] == "done" and item["updated_at"] >= stamp(-7) for item in tasks),
        "hours_logged_last_7_days": round(sum(item.get("duration_minutes") or 0 for item in recent_entries) / 60, 2),
        "outstanding_invoice_total": money(sum(item["total"] for item in invoices if item["status"] in ("sent", "overdue"))),
        "paid_invoice_total_this_month": money(sum(item["total"] for item in invoices if item["status"] == "paid" and item.get("paid_at", "")[:7] == day()[:7])),
        "project_health": health, "upcoming_tasks": upcoming, "revenue_by_month": revenue,
    }


@app.get(API_PREFIX + "/activity")
async def activity(entity_type: str | None = None, entity_id: str | None = None, limit: int = 50, offset: int = 0, ctx: dict[str, Any] = Depends(current_context)):
    items = filtered("activity", ctx["tenant_id"])
    if entity_type: items = [item for item in items if item["entity_type"] == entity_type]
    if entity_id: items = [item for item in items if item["entity_id"] == entity_id]
    return items[offset:offset + max(1, min(limit, 200))]


@app.get(API_PREFIX + "/notifications/unread-count")
async def unread_count(ctx: dict[str, Any] = Depends(current_context)):
    return {"count": sum(not item["is_read"] for item in filtered("notifications", ctx["tenant_id"]))}


@app.get(API_PREFIX + "/notifications")
async def notifications(unread_only: bool = False, page: int = 1, page_size: int = 20, ctx: dict[str, Any] = Depends(current_context)):
    items = filtered("notifications", ctx["tenant_id"])
    if unread_only: items = [item for item in items if not item["is_read"]]
    return paginate(items, page, page_size)


@app.post(API_PREFIX + "/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, ctx: dict[str, Any] = Depends(current_context)):
    notification = next((item for item in filtered("notifications", ctx["tenant_id"]) if item["id"] == notification_id), None)
    if notification: notification["is_read"] = True
    return {"message": "Notification updated."}


@app.post(API_PREFIX + "/notifications/read-all")
async def mark_all_notifications_read(ctx: dict[str, Any] = Depends(current_context)):
    for item in filtered("notifications", ctx["tenant_id"]):
        item["is_read"] = True
    return {"message": "Notifications marked read."}


@app.get(API_PREFIX + "/search")
async def search(q: str = "", ctx: dict[str, Any] = Depends(current_context)):
    needle = q.lower()
    results = []
    for item in filtered("clients", ctx["tenant_id"]):
        if needle in item["name"].lower():
            results.append({"id": item["id"], "type": "client", "title": item["name"], "subtitle": item.get("company"), "url": "/app/clients/" + item["id"]})
    for item in filtered("projects", ctx["tenant_id"]):
        if needle in item["name"].lower():
            results.append({"id": item["id"], "type": "project", "title": item["name"], "subtitle": "Project", "url": "/app/projects/" + item["id"]})
    for item in filtered("tasks", ctx["tenant_id"]):
        if needle in item["title"].lower():
            results.append({"id": item["id"], "type": "task", "title": item["title"], "subtitle": "Task", "url": "/app/projects/" + item["project_id"]})
    return {"query": q, "results": results[:12]}


@app.get(API_PREFIX + "/api-keys")
async def api_keys(ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin"))
    return filtered("apiKeys", ctx["tenant_id"])


@app.post(API_PREFIX + "/api-keys", status_code=201)
async def create_api_key(payload: dict[str, Any] = Body(...), ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin"))
    item = {"id": new_id("key"), "tenant_id": ctx["tenant_id"], "name": payload["name"], "key_prefix": "fd_demo_" + uuid.uuid4().hex[:4], "is_active": True, "last_used_at": None, "created_at": now().isoformat(), "plaintext_key": "fd_demo_local_only_" + uuid.uuid4().hex}
    STATE["apiKeys"].append(item)
    return item


@app.delete(API_PREFIX + "/api-keys/{key_id}")
async def revoke_api_key(key_id: str, ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin"))
    key = next((item for item in filtered("apiKeys", ctx["tenant_id"]) if item["id"] == key_id), None)
    if key: key["is_active"] = False
    return {"message": "API key revoked."}


@app.get(API_PREFIX + "/webhooks")
async def webhooks(ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin"))
    return filtered("webhooks", ctx["tenant_id"])


@app.post(API_PREFIX + "/webhooks", status_code=201)
async def create_webhook(payload: dict[str, Any] = Body(...), ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin"))
    webhook = {"id": new_id("webhook"), "tenant_id": ctx["tenant_id"], "target_url": payload["target_url"], "events": payload.get("events", []), "description": payload.get("description"), "is_active": True, "created_at": now().isoformat(), "secret": "demo_secret_" + uuid.uuid4().hex}
    STATE["webhooks"].append(webhook)
    return webhook


@app.patch(API_PREFIX + "/webhooks/{webhook_id}")
async def update_webhook(webhook_id: str, payload: dict[str, Any] = Body(...), ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin"))
    webhook = next((item for item in filtered("webhooks", ctx["tenant_id"]) if item["id"] == webhook_id), None)
    if not webhook: raise HTTPException(status_code=404, detail="Webhook not found.")
    webhook.update(payload)
    return webhook


@app.delete(API_PREFIX + "/webhooks/{webhook_id}")
async def delete_webhook(webhook_id: str, ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin"))
    STATE["webhooks"] = [item for item in STATE["webhooks"] if not (item["id"] == webhook_id and item["tenant_id"] == ctx["tenant_id"])]
    return {"message": "Webhook removed."}


@app.get(API_PREFIX + "/webhooks/{webhook_id}/deliveries")
async def webhook_deliveries(webhook_id: str, ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin"))
    return [item for item in filtered("webhookDeliveries", ctx["tenant_id"]) if item["webhook_id"] == webhook_id]


@app.get(API_PREFIX + "/attachments")
async def attachments(project_id: str | None = None, ctx: dict[str, Any] = Depends(current_context)):
    items = filtered("attachments", ctx["tenant_id"])
    return [item for item in items if not project_id or item.get("project_id") == project_id]


@app.post(API_PREFIX + "/attachments", status_code=201)
async def upload_attachment(project_id: str, file: UploadFile = File(...), ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin", "member"))
    raw = await file.read()
    item = {"id": new_id("attachment"), "tenant_id": ctx["tenant_id"], "project_id": project_id, "task_id": None, "uploaded_by_id": ctx["user"]["id"], "file_name": file.filename or "demo-upload", "content_type": file.content_type or "application/octet-stream", "size_bytes": len(raw), "created_at": now().isoformat(), "simulated": True}
    STATE["attachments"].append(item)
    add_activity(ctx, "attachment.uploaded", "project", project_id, item["file_name"])
    return item


@app.delete(API_PREFIX + "/attachments/{attachment_id}")
async def delete_attachment(attachment_id: str, ctx: dict[str, Any] = Depends(current_context)):
    require_role(ctx, ("owner", "admin", "member"))
    STATE["attachments"] = [item for item in STATE["attachments"] if not (item["id"] == attachment_id and item["tenant_id"] == ctx["tenant_id"])]
    return {"message": "Attachment removed."}


if __name__ == "__main__":
    import uvicorn

    print("Starting FlowDesk IN-MEMORY DEMO API on http://127.0.0.1:8001")
    print("No production database, email, webhook delivery, or file storage is used.")
    print("Demo state resets when this process stops. Do not expose this service publicly.")
    uvicorn.run(app, host="127.0.0.1", port=8001, reload=False)
