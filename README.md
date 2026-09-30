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

## Local
```
cp .env.example .env
docker compose up
```

Python-only:
```
python -m pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

In non-development environments set a strong JWT_SECRET_KEY and COOKIE_SECURE=true.
