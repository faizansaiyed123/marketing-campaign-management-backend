# Marketing Campaign Management — Backend

FastAPI + SQLAlchemy 2 + PostgreSQL + Alembic.

Authentication uses Argon2id password hashes and JWTs stored in an HttpOnly, SameSite=Strict cookie. Core campaign data remains PostgreSQL-backed and isolated by owner.

Campaigns target an owned audience, may be scheduled, and can be executed into a durable delivery outbox. SMTP is optional; when it is not configured, the run stays explicitly queued rather than pretending that messages were sent. When SMTP is configured, queued deliveries are sent through the standard SMTP protocol.

Reports and the analytics overview are derived only from stored delivery and tracking events.

## Local run
```bash
cp .env.example .env
docker compose up -d postgres
python -m pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

Swagger UI is available at `/docs`.
