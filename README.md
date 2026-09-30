# Marketing Campaign Management — Backend

FastAPI, SQLAlchemy 2, PostgreSQL, Alembic.

### Implemented
- Registration, login, logout and current-user session.
- Argon2id password hashing and HttpOnly/SameSite=Strict JWT cookie authentication.
- Owner-scoped audiences and contacts with relational constraints.
- Campaign creation/editing, scheduled state, execution into a durable delivery outbox.
- Optional SMTP delivery using Python's standard SMTP client; queued deliveries are never mislabeled as sent.
- Campaign reports and aggregate analytics derived from stored delivery/tracking events.
- PostgreSQL migration checked in under Alembic.

### Run locally
```
cp .env.example .env
docker compose up -d postgres
python -m pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

OpenAPI docs: `http://127.0.0.1:8000/docs`.
