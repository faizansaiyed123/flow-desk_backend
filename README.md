# FlowDesk Backend

FlowDesk Backend is the API service for FlowDesk, a multi-tenant workspace application for managing clients, projects, tasks, time tracking, invoices, team access, and integrations. It is built with FastAPI, asynchronous SQLAlchemy, and PostgreSQL, with Alembic for database migrations.

> **Visual walkthrough:** [Explore the FlowDesk full-stack walkthrough](https://github.com/faizansaiyed123/flow-desk_frontend/blob/main/docs/testing/VISUAL-TEST-WALKTHROUGH.md) to see the application workflows and their screenshots.

## Key Features

- **Authentication and workspaces:** Account registration, login, token refresh, password recovery and change, workspace switching, membership management, role-based permissions, and invitation workflows.
- **Client and project management:** Create, list, update, archive, and delete clients; manage projects and their status; and retrieve project and client statistics.
- **Task management:** Retrieve Kanban boards, create and update tasks, move tasks between statuses, assign workspace members, and manage task comments.
- **Time tracking and invoicing:** Record manual time entries, start and stop timers, track billable time, create invoices, generate invoices from time entries, and manage invoice status transitions.
- **Workspace visibility:** Dashboard summaries, activity logs, global search, and user notifications.
- **Integrations and attachments:** Create and revoke API keys, configure webhooks and inspect delivery history, and upload, list, download, and delete file attachments.

## Tech Stack and Architecture

- **Language and API:** Python 3.12, FastAPI, and Uvicorn.
- **Database:** PostgreSQL, SQLAlchemy's asynchronous ORM, and `asyncpg`.
- **Migrations:** Alembic manages database schema changes.
- **Validation and settings:** Pydantic, Pydantic Settings, and typed request and response schemas.
- **Authentication:** Password hashing with bcrypt and signed JWT access and refresh tokens.
- **Authorization:** Tenant-scoped authentication context and membership-role checks for protected operations.
- **Integrations:** HTTPX for webhook requests and SMTP configuration for transactional email.
- **File storage:** Attachments are stored on local disk in tenant-specific directories.

API routes are registered in `app/main.py`. Route handlers use service modules for business logic, while SQLAlchemy models define database entities. Database sessions commit on successful completion and roll back on exceptions.

API keys are stored as hashes, with the plaintext key returned to the caller only when the key is created. When an SMTP host is not configured, the email service logs messages rather than sending them.

## Companion Repository

The frontend is maintained separately:

- [FlowDesk Frontend](https://github.com/faizansaiyed123/flow-desk_frontend)

The frontend repository also contains the [visual walkthrough](https://github.com/faizansaiyed123/flow-desk_frontend/blob/main/docs/testing/VISUAL-TEST-WALKTHROUGH.md) and [API and feature coverage inventory](https://github.com/faizansaiyed123/flow-desk_frontend/blob/main/docs/testing/ENDPOINT-COVERAGE.md).

## Quick Start

### Prerequisites

- Python 3.12, as specified by the Dockerfile.
- PostgreSQL.
- Docker, if running the containerized version.

### Local Setup

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

Create a PostgreSQL database and configure `SECRET_KEY` and `DATABASE_URL` in `.env` for your environment.

Apply the database migrations:

```bash
alembic upgrade head
```

Start the API:

```bash
uvicorn app.main:app --reload
```

The health endpoint is available at `/health`. FastAPI's interactive API documentation is available at `/docs` and `/redoc` when the application is not running in production mode.

### Docker

Build the image:

```bash
docker build -t flowdesk-backend .
```

Run migrations as a separate step:

```bash
docker run --rm --env-file .env flowdesk-backend alembic upgrade head
```

Start the API:

```bash
docker run --rm --env-file .env -p 8000:8000 flowdesk-backend
```

Configure `DATABASE_URL` to point to a PostgreSQL instance reachable from inside the container. This repository provides a Dockerfile but does not include a Docker Compose file. Migrations are not automatically applied when the API container starts.

## Environment Variables

The available names below are taken from [.env.example](.env.example). Configure values appropriate for your environment without committing secrets.

| Category | Variable names |
|---|---|
| Application | `APP_NAME`, `ENVIRONMENT`, `DEBUG`, `API_V1_PREFIX` |
| Security | `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `ALGORITHM` |
| Database | `DATABASE_URL`, `DATABASE_ECHO` |
| Cross-origin access | `CORS_ORIGINS` |
| File uploads | `UPLOAD_DIR`, `MAX_UPLOAD_SIZE_MB` |
| Email | `EMAIL_ENABLED`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` |
| Frontend links | `FRONTEND_URL` |
| Optional integration configuration | `REDIS_URL` |

## Tests

Install the development dependencies using `requirements-dev.txt`, then run:

```bash
pytest -q
```

The test suite requires PostgreSQL. Its fixtures create and drop database tables and clear data between tests. Use a dedicated, disposable test database and ensure `DATABASE_URL` targets that database before running tests.

The companion frontend repository contains the [full-stack verification workflow](https://github.com/faizansaiyed123/flow-desk_frontend/blob/main/.github/workflows/full-stack-e2e.yml), which runs backend tests and browser-based integration checks against PostgreSQL.

## Project Structure

```text
flow-desk_backend/
├── app/
│   ├── core/           # Authentication context, exceptions, pagination
│   ├── models/         # SQLAlchemy database models
│   ├── routers/        # FastAPI route handlers
│   ├── schemas/        # Request and response schemas
│   ├── services/       # Application and domain logic
│   ├── config.py       # Application settings
│   ├── database.py     # Database engine and sessions
│   ├── dependencies.py # Authentication and authorization
│   ├── main.py         # FastAPI application entrypoint
│   └── security.py     # Password, token, and key helpers
├── alembic/
│   └── versions/       # Database migration scripts
├── tests/              # Pytest test suite
├── uploads/            # Local attachment storage directory
├── .env.example        # Environment configuration template
├── Dockerfile          # Container build configuration
├── alembic.ini         # Alembic configuration
├── requirements.txt    # Runtime dependencies
└── requirements-dev.txt # Development and test dependencies
```

## Documentation

- [Visual full-stack walkthrough](https://github.com/faizansaiyed123/flow-desk_frontend/blob/main/docs/testing/VISUAL-TEST-WALKTHROUGH.md)
- [API and feature coverage inventory](https://github.com/faizansaiyed123/flow-desk_frontend/blob/main/docs/testing/ENDPOINT-COVERAGE.md)
- [Full-stack verification workflow](https://github.com/faizansaiyed123/flow-desk_frontend/blob/main/.github/workflows/full-stack-e2e.yml)
- [Database migrations](alembic/versions/)
- [Alembic configuration](alembic.ini)
- [Environment template](.env.example)
- [Dockerfile](Dockerfile)
