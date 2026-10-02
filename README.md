# Marketing Campaign Management — Backend

FastAPI + SQLAlchemy 2 + PostgreSQL + Alembic.

Core workflows:
- Secure account registration/login/logout using Argon2id passwords and an HttpOnly, SameSite=Strict JWT cookie.
- Owner-scoped audience and contact management, including subscription preferences.
- Campaign creation, editing, scheduling and execution.
- Durable delivery records with optional standard SMTP delivery.
- Open tracking through a real 1x1 GIF endpoint and aggregate reporting from persisted delivery/event records.
- Lightweight 15-second scheduler worker; no Redis/Celery/Kafka is required.
- PostgreSQL relational constraints, indexes and Alembic migrations.

Without SMTP, execution intentionally remains queued and never reports a message as sent.

## Requirements

- Docker Engine/Desktop with Docker Compose v2 for the Docker workflow.
- Python 3.11+ and pip for the Python-only workflow.
- SMTP credentials are optional. Without SMTP configuration, campaign deliveries remain queued by design.

## One-command backend startup

From the backend repository, run:

```bash
python run.py
```

`run.py` is backend-only. It starts the existing Docker Compose stack and keeps these backend components running together:

- PostgreSQL 16 on port 5432.
- FastAPI on port 8000, including the existing Alembic migration step before API startup.
- The existing database-backed scheduler worker, which runs every 15 seconds.

The script waits for the API's `/health` endpoint, which also verifies PostgreSQL connectivity, before reporting the backend as ready. Press `Ctrl+C` to stop the stack; the script runs `docker compose down` for the services it started.

Redis, Celery, RabbitMQ and Kafka are not started because this backend does not require them.

For a custom health URL, set `BACKEND_HEALTH_URL` before running the script. The normal development value is `http://127.0.0.1:8000/health`.

## Docker

The backend repository is independently runnable:

```bash
docker compose up --build
```

This starts:
- PostgreSQL 16 on port 5432.
- FastAPI on port 8000.
- The existing scheduler worker that checks for due/queued campaigns every 15 seconds.

The API container waits for PostgreSQL health before starting and applies Alembic migrations before launching FastAPI. The worker starts after the API health check succeeds.

The API health endpoint is:

```
http://localhost:8000/health
```

### Environment variables

The application reads its existing settings from `.env`. The Docker Compose development stack supplies the database connection and development runtime settings directly so it can start without a manually created `.env`.

For non-Docker or custom deployments, copy the example:

```bash
cp .env.example .env
```

Important variables include:
- `DATABASE_URL`
- `JWT_SECRET_KEY`
- `FRONTEND_ORIGIN`
- `COOKIE_SECURE`
- `PUBLIC_BASE_URL`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM_EMAIL`
- `SMTP_USE_TLS`

Do not commit real secrets.

For non-development environments, use a strong `JWT_SECRET_KEY`, `COOKIE_SECURE=true`, HTTPS `PUBLIC_BASE_URL` and HTTPS `FRONTEND_ORIGIN`, as enforced by the existing runtime validation.

### Database and migrations

PostgreSQL is required by the normal Docker development stack. The database is persisted in the `campaign_postgres` Docker volume.

The API image runs:

```bash
alembic upgrade head
```

before starting Uvicorn, so the database schema is brought up to the current migration before the API accepts traffic.

For the Python-only workflow, PostgreSQL must already be running and reachable through `DATABASE_URL`:

```bash
python -m pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

### Redis / queues / workers

Redis, Celery, RabbitMQ and Kafka are not part of this application. The existing `app.worker` process is a lightweight database-backed scheduler/worker and is included as a separate Compose service.

### SMTP

SMTP is optional. When `SMTP_HOST` and `SMTP_FROM_EMAIL` are not configured, execution creates durable queued deliveries but does not mark them as sent.

When SMTP is configured, the existing delivery service sends messages through the configured SMTP server and records sent/failed delivery state.

### Stop

```bash
docker compose down
```

To also remove the persisted PostgreSQL development volume:

```bash
docker compose down -v
```

### Rebuild

```bash
docker compose up --build
```

## Frontend integration

The separately maintained frontend uses the existing `VITE_API_URL` variable and defaults to:

```
http://localhost:8000
```

When running both repositories locally, start the backend on port 8000 and configure the frontend's `VITE_API_URL` to that address.

The backend allows credentialed CORS only for the configured `FRONTEND_ORIGIN`.

## Local development

```bash
python -m pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

The existing frontend Playwright integration tests start the backend with Uvicorn and expect the backend health endpoint on port 8000. The test configuration can use an existing backend directory through `BACKEND_DIR`.

## API

FastAPI's generated API documentation is available at:

```
http://localhost:8000/docs
```
