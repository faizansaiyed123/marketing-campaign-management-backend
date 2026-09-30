# Marketing Campaign Management — Backend

FastAPI + SQLAlchemy 2 + PostgreSQL + Alembic.

The backend provides authenticated campaign management, audiences/contacts, scheduled campaign state, durable delivery records, optional SMTP delivery, tracking events, and analytics. Passwords are Argon2id-hashed; the session JWT is stored in an HttpOnly, SameSite=Strict cookie.

Scheduling is persisted with scheduled_at. The lightweight worker polls every 15 seconds, queues due campaigns, and attempts SMTP delivery when configured. No Redis, Celery, Kafka, or paid provider is required.

## Run
```bash
cp .env.example .env
docker compose up
```

For a Python-only API:
```bash
python -m pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

OpenAPI docs are served at /docs.
