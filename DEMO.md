# FlowDesk backend demo

This `demo` branch adds a standalone in-memory FastAPI API simulator for recruiter walkthroughs. It is intentionally separate from the production FlowDesk application and does not use PostgreSQL, SQLAlchemy, Alembic, Redis, SMTP, production storage, or the existing database-backed test fixtures.

## Start

From the backend repository's `demo` branch:

```bash
python -m venv .venv
# Activate the environment, then:
python -m pip install -r requirements-dev.txt
python demo_app.py
```

The API binds only to `http://127.0.0.1:8001`. Interactive docs are at `http://127.0.0.1:8001/docs`; health check: `http://127.0.0.1:8001/health`.

## Demo accounts

All accounts use password `Demo1234!`.

| Role | Email |
|---|---|
| Owner | `alex@northstar.demo` |
| Admin | `jordan@northstar.demo` |
| Member | `sam@northstar.demo` |
| Viewer | `taylor@northstar.demo` |

The Northstar Creative workspace includes example clients, active/on-hold/planning projects, Kanban tasks across all statuses, team members, comments, billable time entries, paid/sent/overdue/draft invoices, notifications, and activity. The owner also belongs to a second workspace, FlowDesk Labs, to demonstrate tenant switching and data separation.

## Optional frontend integration

The companion frontend demo works browser-locally by default and does not require this API. To deliberately connect the frontend to this backend simulator, set frontend `.env.local` to:

```env
VITE_FLOWDESK_BROWSER_DEMO=false
VITE_API_BASE_URL=http://127.0.0.1:8001/api/v1
```

Restart Vite after changing the environment. Use the same demo credentials above.

## Simulation and safety boundaries

- All state exists in process memory and resets when the server restarts.
- No production application modules, PostgreSQL, or migrations are imported or run.
- Email/reset messages, webhooks, API key values, notifications, and file attachments are demonstrations. No external emails, webhook requests, payments, or persistent file uploads occur.
- This API intentionally has demo-only authentication and must not be deployed, exposed to a public interface, connected to production data, or used with real customer data.
- It listens on loopback only (`127.0.0.1`).

## Tests

The demo tests live in `demo_tests/` and are isolated from the production test fixtures, which expect a real PostgreSQL test database and manage its schema.

```bash
python -m pytest -q demo_tests
```
