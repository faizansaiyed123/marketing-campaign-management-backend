# Marketing Campaign Management — Backend

FastAPI + SQLAlchemy 2 + PostgreSQL + Alembic.

Core workflows:
- Secure account registration/login/logout using Argon2id passwords and an HttpOnly, SameSite=Strict JWT cookie.
- Owner-scoped audience and contact management, including subscription preferences.
- Campaign creation, editing, scheduling and execution.
- Reusable, owner-scoped campaign templates with create/edit/delete workflows.
- Durable delivery records; actual SMTP sending runs in the background worker. The worker atomically claims only campaigns that remain scheduled and due, rechecks subscription status immediately before sending, and reports skipped recipients separately from sent/failed deliveries.
- Campaign reports aggregate delivery attempts in PostgreSQL rather than loading every delivery into the API process. The total is cumulative across retries; latest_run_status identifies the latest run separately.
- Open tracking through a real 1x1 GIF endpoint, click tracking restricted to links present in that specific campaign delivery, and aggregate reporting from persisted delivery/event records.
- Database-backed 15-second campaign worker plus Redis-backed shared authentication rate limits. Redis is included in Compose; Celery, RabbitMQ and Kafka are not required.
- PostgreSQL relational constraints, indexes and Alembic migrations.

Development can run without SMTP; deliveries remain queued until mail is configured. Production startup rejects missing SMTP configuration so a live production API cannot silently accept campaigns it cannot send.

## Requirements

- Docker Engine/Desktop with Docker Compose v2 for the Docker workflow.
- Python 3.11+ and pip for the Python-only workflow.
- SMTP is optional only in development/tests. Production requires SMTP host, sender address, TLS, and a matching username/password pair when the provider requires authentication.

## One-command backend startup

From the backend repository, run:

```bash
python run.py
```

`run.py` is backend-only. It starts the existing Docker Compose stack and keeps these backend components running together:

- PostgreSQL 16 on port 5432.
- FastAPI on port 8000, including the existing Alembic migration step before API startup.
- Redis 7 (private, password-protected; shared authentication rate-limit storage).
- The existing database-backed scheduler/SMTP worker, which runs every 15 seconds.

The script waits for the API's `/health` endpoint, which also verifies PostgreSQL connectivity, before reporting the backend as ready. Press `Ctrl+C` to stop the stack; the script runs `docker compose down` for the services it started.

Redis is started for shared authentication rate-limit counters. Celery, RabbitMQ and Kafka are unnecessary: campaign jobs and delivery state remain durable in PostgreSQL.

For a custom health URL, set `BACKEND_HEALTH_URL` before running the script. The normal development value is `http://127.0.0.1:8000/health`.

## Docker

The backend repository is independently runnable:

```bash
docker compose up --build
```

This starts:
- PostgreSQL 16 on port 5432.
- FastAPI on port 8000.
- Redis 7, privately available to the API and worker for shared rate-limit counters.
- The existing scheduler/SMTP worker that checks for due/queued campaigns every 15 seconds.

The API container waits for PostgreSQL health before starting and applies Alembic migrations before launching FastAPI. The worker starts after the API health check succeeds.

For local development, Compose binds the database and API host ports to loopback only; Redis has no published host port. Do not expose the raw HTTP API port or PostgreSQL directly to the public internet. Production login and registration limits use atomic Redis-backed rolling windows shared across API workers/replicas: 10 login attempts per source IP per minute and 5 registrations per source IP per hour. If Redis is unavailable or its URL is missing, authentication fails closed with HTTP 503 rather than bypassing the protection. Caddy overwrites X-Forwarded-For with the client address it sees; Uvicorn trusts only Caddy's fixed address on the private proxy network, not the whole Docker bridge range. The included Caddyfile terminates TLS and routes traffic, while application rate limiting is handled by Redis.

The API readiness endpoint verifies PostgreSQL and, in production, the shared Redis authentication-rate-limit store. It returns HTTP 503 when either required service is unavailable, so a healthy status doesn't hide an authentication-protection outage.

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
- `REDIS_PASSWORD` and (for non-Compose runs) `REDIS_URL`
- `FORWARDED_ALLOW_IPS` (defaults to `172.30.240.2,127.0.0.1`; keep the Caddy IP and this list synchronized if you change the proxy network)
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM_EMAIL`
- `SMTP_USE_TLS` (STARTTLS, commonly port 587)
- `SMTP_USE_SSL` (implicit TLS, commonly port 465; do not enable both)

Do not commit real secrets.

For non-development environments, use unique random `JWT_SECRET_KEY`, `POSTGRES_PASSWORD`, and `REDIS_PASSWORD`, `COOKIE_SECURE=true`, `COOKIE_NAME=__Host-campaign_session`, HTTPS `PUBLIC_BASE_URL` and `FRONTEND_ORIGIN`. Production startup rejects common JWT/database placeholders, database passwords shorter than 24 characters, weak or missing Redis credentials, malformed/non-origin HTTPS URL settings, missing SMTP host/sender, mismatched SMTP login credentials, and configurations where neither or both SMTP TLS modes are enabled. Never deploy with the development-only Redis password. Keep Redis private; Compose does not publish its port. Set a unique `POSTGRES_PASSWORD` for Docker Compose deployments; the Python-only workflow uses the credentials in `DATABASE_URL`. Docker Compose passes `COOKIE_NAME` to both the API and worker. Because the session cookie is `SameSite=Strict`, deploy the frontend and API on HTTPS custom domains under the same registrable domain (for example, `app.example.com` and `api.example.com`). Unrelated default provider domains may cause browsers to block the session cookie.

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

Redis is used for shared atomic login/registration rate-limit counters and runs privately in Compose with password authentication and a persistent data volume. It is not the campaign job queue: PostgreSQL stores durable campaign runs and deliveries. The separate `app.worker` process checks scheduled campaigns every 15 seconds and sends queued email through SMTP, recording delivery outcomes in PostgreSQL. Its atomic claim rechecks the persisted campaign state and due time, so an edit that changes a campaign back to draft prevents a stale scheduler selection from executing it. Celery, RabbitMQ and Kafka are not required.

### SMTP

Campaign subjects and HTML bodies support `{{first_name}}`, `{{last_name}}`, `{{full_name}}`, and `{{email}}` contact placeholders. Unknown placeholders are left unchanged; contact values are escaped before being inserted into HTML.

SMTP may be omitted in development; in that case campaign execution creates durable queued deliveries and never marks them sent. Production settings require `SMTP_HOST`, `SMTP_FROM_EMAIL`, either certificate-verified STARTTLS (`SMTP_USE_TLS=true`, commonly port 587) or certificate-verified implicit TLS (`SMTP_USE_SSL=true`, commonly port 465), and matching `SMTP_USERNAME`/`SMTP_PASSWORD` when authentication is used. The two TLS modes are mutually exclusive. Configure these values for your provider in the server's untracked `.env`. The API endpoint queues work and returns HTTP 202 without sending each email inside the request. The background worker sends messages and records sent/failed outcomes. It rechecks each contact under a row lock immediately before sending; contacts that unsubscribed after queueing are skipped and counted separately. SMTP recipient-refusal responses are recorded as failures instead of being falsely marked sent. A configured-but-invalid provider credential can only be confirmed by a real SMTP connection/delivery test.

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

## PostgreSQL backups and recovery

Create a custom-format PostgreSQL dump, verify it with `pg_restore --list`, and keep it outside the Git repository:

```bash
bash scripts/backup_postgres.sh
```

The default local location is `~/campaign-management-backups`; set `BACKUP_DIR` and `BACKUP_RETENTION_DAYS` to customize storage and retention. The dump file is restricted to owner-only permissions. A local-only backup does not protect against server loss.

For an off-host copy, configure rclone on the server and set `BACKUP_RCLONE_REMOTE`, for example `encrypted-backups:campaign-management`. Use an rclone **crypt** remote or another client-side encrypted destination for contact data. The backup script reports an error if a configured off-host copy fails.

Recovery is deliberately performed into a **separate database** to avoid overwriting the live campaign database. Validate the archive and restore it to a new name:

```bash
RESTORE_DATABASE=campaigns_restore_20261020 bash scripts/restore_postgres.sh ~/campaign-management-backups/campaigns-YYYYMMDDTHHMMSSZ.dump
```

After checking the restored database, switch `POSTGRES_DB` in the server's untracked `.env` to the restore database name and recreate the PostgreSQL/API/worker containers using the same base/production Compose files used for deployment. The restored database must be compatible with the running application's Alembic revision. Test this procedure periodically; no backup is proven recoverable until an actual restore has succeeded.

## Single-host production deployment (Caddy + HTTPS)

The optional docker-compose.production.yml overlay adds Caddy as the public TLS-terminating reverse proxy. It serves the frontend at FRONTEND_DOMAIN and routes the API at API_DOMAIN. Caddy obtains and renews certificates automatically when both DNS records point to this server and inbound ports 80 and 443 are reachable. The production overlays require database/Redis/JWT values, HTTPS origins, domains, and SMTP fields during Compose config resolution, so missing or empty settings fail before containers start. The API rejects obvious placeholders, malformed sender addresses, and insecure settings during startup; actual SMTP credentials and deliverability still require a controlled-inbox send test.

This setup uses Docker Compose, Caddy, and PostgreSQL without a paid proxy service. It assumes a Linux server/VPS with Docker Engine and Compose v2, public DNS control, and a persistent disk. It does **not** provision the server, DNS, firewall, or SMTP account for you.

1. Create the shared Docker network once per server. First check that `172.30.240.0/24` does not conflict with a LAN, VPN, or an existing Docker network; choose another unused private subnet if needed. Caddy uses the fixed address `172.30.240.2`, and Uvicorn trusts only that address for forwarded headers:

   ```bash
   docker network create --driver bridge --subnet 172.30.240.0/24 --gateway 172.30.240.1 campaign_proxy
   ```

   If you choose another subnet, update the Caddy static address in `docker-compose.production.yml` and `FORWARDED_ALLOW_IPS` in the backend `.env` together.

2. In the backend repository, copy `.env.example` to `.env` and set these production values. Generate the secrets on the server; never commit `.env`:

   ```env
   ENVIRONMENT=production
   POSTGRES_USER=campaign_app
   POSTGRES_DB=campaigns
   POSTGRES_PASSWORD=<output of openssl rand -hex 24>
   JWT_SECRET_KEY=<output of openssl rand -hex 32>
   REDIS_PASSWORD=<output of openssl rand -hex 24>
   FORWARDED_ALLOW_IPS=172.30.240.2,127.0.0.1
   SMTP_HOST=smtp.your-provider.example
   SMTP_PORT=587
   SMTP_USERNAME=<provider username, if required>
   SMTP_PASSWORD=<provider password or app password, if required>
   SMTP_FROM_EMAIL=<verified sender address>
   SMTP_USE_TLS=true
   SMTP_USE_SSL=false
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

6. Verify `https://api.example.com/health`, open `https://app.example.com`, then test registration/login/logout, template owner isolation, audience/contact changes, campaign scheduling, and tracking. Send a real test campaign to a controlled inbox and confirm the provider accepts it and the report records it as sent. Production startup requires SMTP settings, but valid credentials, sender verification, DNS email authentication (SPF/DKIM/DMARC), provider acceptance, and inbox placement must be validated with your provider.

The production overlay publishes only Caddy's 80/443 ports publicly. It retains the named PostgreSQL volume and Caddy certificate/configuration volumes across container recreation. Back up PostgreSQL and its volume separately; Docker volumes alone are not off-host backups. Use `docker compose -f docker-compose.yml -f docker-compose.production.yml logs -f api worker caddy` to inspect logs.

For a managed hosting provider or a pre-existing reverse proxy, use that platform's HTTPS and persistent-database facilities instead; this Caddy overlay is optional.

## Deploy frontend on your existing Vercel project

The frontend repository includes Vercel configuration for its Vite build and SPA routing. Use this API-only backend overlay if Vercel serves the frontend; do not start both the API-only overlay and the full two-domain Caddy overlay on the same server because both publish ports 80/443.

1. In your existing Vercel dashboard, import/select the GitHub frontend repository, set the production branch to `main`, and keep the project root at the repository root.
2. Set the Production environment variable `VITE_API_URL=https://api.your-real-domain.example` in Project Settings → Environment Variables. This variable is public and embedded at build time. Trigger a new production deployment after changing it.
3. Assign a custom HTTPS frontend domain such as `app.your-real-domain.example` to the Vercel project. Use an API subdomain under the same registrable domain (for example, `api.your-real-domain.example`) so the backend's `SameSite=Strict` session cookie works.
4. Point the API subdomain's DNS record to your Linux server, then use `docker-compose.api-production.yml` with `Caddyfile.api-only`. Create the shared network using the documented subnet and set `API_DOMAIN`, `FRONTEND_ORIGIN` to the exact Vercel custom-domain origin, `PUBLIC_BASE_URL` to the API HTTPS origin, strong DB/JWT/Redis secrets, and working SMTP settings in the backend's untracked `.env`.
5. Deploy the backend with:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.api-production.yml up --build -d
   ```

6. Test login/session/logout and a controlled-inbox campaign from the Vercel production domain. Vercel preview URLs are different origins and are not allowed to use the production API by default; keep production API access restricted to the exact configured frontend origin.

The full `docker-compose.production.yml` remains available if both frontend and backend are served by Docker/Caddy on the same host instead of Vercel.

## Frontend integration

The separately maintained frontend uses the existing `VITE_API_URL` variable and defaults to:

```
http://localhost:8000
```

When running both repositories locally, start the backend on port 8000 and configure the frontend's `VITE_API_URL` to that address.

The backend allows credentialed CORS only for the configured `FRONTEND_ORIGIN`. Unsafe `/api/v1/` requests also reject a foreign `Origin` header and reject cross-site Fetch Metadata when `Origin` is absent; this is additional CSRF defense for cookie-authenticated actions across sibling subdomains. Non-browser clients that omit both headers remain supported.

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
