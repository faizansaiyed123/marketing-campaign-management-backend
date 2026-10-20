# Marketing Campaign Management — Backend

FastAPI + SQLAlchemy 2 + PostgreSQL + Alembic.

Core workflows:
- Secure account registration/login/logout using Argon2id passwords and an HttpOnly, SameSite=Strict JWT cookie.
- Owner-scoped audience and contact management, including subscription preferences.
- Campaign creation, editing, scheduling and execution.
- Reusable, owner-scoped campaign templates with create/edit/delete workflows.
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

For local development, Compose binds the database and API ports to loopback only. Do not expose the raw HTTP API port directly to the public internet. In production, route public HTTPS traffic through a TLS-terminating reverse proxy or managed HTTPS load balancer, and keep PostgreSQL private. The API container runs as a non-root user. Configure gateway/reverse-proxy rate limits for login and registration; the application does not currently implement a shared distributed rate limiter.

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
- `POSTGRES_PASSWORD` (Docker Compose database credential)
- `JWT_SECRET_KEY`
- `FRONTEND_ORIGIN`
- `COOKIE_SECURE`
- `COOKIE_NAME`
- `PUBLIC_BASE_URL`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM_EMAIL`
- `SMTP_USE_TLS`

Do not commit real secrets.

For non-development environments, use a unique randomly generated `JWT_SECRET_KEY`, `COOKIE_SECURE=true`, `COOKIE_NAME=__Host-campaign_session`, HTTPS `PUBLIC_BASE_URL` and HTTPS `FRONTEND_ORIGIN`. Production startup rejects common secret placeholders, the development PostgreSQL password, and enforces these cookie/HTTPS requirements. Set a unique `POSTGRES_PASSWORD` for Docker Compose deployments; the Python-only workflow uses the credentials in `DATABASE_URL`. Docker Compose passes `COOKIE_NAME` to both the API and worker. Because the session cookie is `SameSite=Strict`, deploy the frontend and API on HTTPS custom domains under the same registrable domain (for example, `app.example.com` and `api.example.com`). Unrelated default provider domains may cause browsers to block the session cookie.

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

## Single-host production deployment (Caddy + HTTPS)

The optional `docker-compose.production.yml` overlay adds Caddy as the public TLS-terminating reverse proxy. It serves the frontend at `FRONTEND_DOMAIN` and routes the API at `API_DOMAIN`. Caddy obtains and renews certificates automatically when both DNS records point to this server and inbound ports 80 and 443 are reachable.

This setup uses Docker Compose, Caddy, and PostgreSQL without a paid proxy service. It assumes a Linux server/VPS with Docker Engine and Compose v2, public DNS control, and a persistent disk. It does **not** provision the server, DNS, firewall, or SMTP account for you.

1. Create the shared Docker network once per server:

   ```bash
   docker network create campaign_proxy
   ```

2. In the backend repository, copy `.env.example` to `.env` and set these production values. Generate the secrets on the server; never commit `.env`:

   ```env
   ENVIRONMENT=production
   POSTGRES_USER=campaign_app
   POSTGRES_DB=campaigns
   POSTGRES_PASSWORD=<output of openssl rand -hex 24>
   JWT_SECRET_KEY=<output of openssl rand -hex 32>
   FRONTEND_DOMAIN=app.example.com
   API_DOMAIN=api.example.com
   FRONTEND_ORIGIN=https://app.example.com
   PUBLIC_BASE_URL=https://api.example.com
   COOKIE_SECURE=true
   COOKIE_NAME=__Host-campaign_session
   ```

   Use your real domains, not the example ones. The example hexadecimal database password avoids URL-reserved characters in the Compose-generated SQLAlchemy URL. Choose the database password before the first start; changing only the environment variable later does not rotate the password inside an already initialized PostgreSQL volume.

3. Create the DNS A/AAAA records for both domains pointing at the server's public address. Allow inbound TCP 80/443 (and optionally UDP 443 for HTTP/3) and administrative SSH only. Keep PostgreSQL and the API's direct host ports bound to loopback.

4. Start the backend API, worker, database, and Caddy proxy:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.production.yml up --build -d
   ```

5. In the frontend repository, create its own untracked `.env` containing `VITE_API_URL=https://api.example.com`, then start its production overlay:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.production.yml up --build -d
   ```

6. Verify `https://api.example.com/health`, open `https://app.example.com`, then test registration/login/logout, template owner isolation, audience/contact changes, and campaign lifecycle. SMTP must be configured and verified separately before claiming real email delivery. Until SMTP is configured, queued deliveries are expected.

The production overlay publishes only Caddy's 80/443 ports publicly. It retains the named PostgreSQL volume and Caddy certificate/configuration volumes across container recreation. Back up PostgreSQL and its volume separately; Docker volumes alone are not off-host backups. Use `docker compose -f docker-compose.yml -f docker-compose.production.yml logs -f api worker caddy` to inspect logs.

For a managed hosting provider or a pre-existing reverse proxy, use that platform's HTTPS and persistent-database facilities instead; this Caddy overlay is optional.

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
