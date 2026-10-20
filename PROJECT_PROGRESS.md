# Project Progress — Marketing Campaign Management Backend

## Objective and current status
Prepare the backend for reliable frontend integration and production deployment.
- Application hardening, reusable templates, container hardening, rate-limit protection, and optional self-hosted HTTPS deployment configuration are committed on `main`.
- Latest backend CI passed PostgreSQL-backed API tests, migrations/parity, both Compose configurations, Caddyfile validation, image build, and non-root runtime verification.
- No live deployment has been performed. A real server, DNS records, production secrets, and optional SMTP credentials remain external setup requirements.

## Repository and latest verified revision
- Repository: https://github.com/faizansaiyed123/marketing-campaign-management-backend
- Target branch: `main`
- Latest application/security commit at this progress checkpoint: `9e08b9ef9a11f4ed22041dd6870c5a0ae7e19bd8` — rate limit authentication attempts.
- Previous deployment configuration commit: `75eed90918332fe88e4ae8bd8566da18ba288fee` — add Caddy + production Compose overlay.
- Previous core API/template revision: `c437bb7d91a0abb373f0e61f1442e61a03f55f1a`.
- Local cloning was unavailable because github.com did not resolve from the local execution environment. Commits were made via the connected GitHub integration; no local uncommitted changes are pending.

## Application features and architecture
- FastAPI + SQLAlchemy + PostgreSQL + Alembic.
- Argon2 password hashing and JWT-backed HttpOnly session cookie; secure cookie deletion; production checks for common JWT/database credential placeholders, HTTPS origins, Secure cookies, and `__Host-` cookie names.
- Owner-scoped audiences, contacts and subscription preferences; campaign create/edit/schedule/execute/report; durable delivery state; click/open/unsubscribe tracking; dashboard and analytics.
- Owner-scoped reusable email templates at `/api/v1/templates`, backed by migration `0003_campaign_templates`.
- Database-backed scheduled/queued worker runs separately and polls every 15 seconds. SMTP is optional; without it, campaign deliveries remain queued and are not falsely marked sent.
- Basic process-local authentication abuse protection:
  - Login: 10 requests per source IP per rolling minute.
  - Registration: 5 requests per source IP per rolling hour.
  - Disabled in development/test to keep integration tests and local development predictable.
  - Counters are in memory and reset on restart; they are not shared across API processes/replicas. If horizontally scaling, run multiple workers, or placing the service behind a different gateway, add a shared distributed rate limiter at the gateway/application layer.

## Production container and reverse proxy
- Backend image uses UID 10001, runs Uvicorn with proper signal handoff after applying Alembic migrations, and adds response security/cache headers.
- Base Compose binds the API and PostgreSQL host ports to loopback; it does not expose them directly to the internet.
- Optional `docker-compose.production.yml` adds Caddy for TLS termination and domain-based routing, while persisting certificate/configuration data.
- Backend API joins the external Docker network `campaign_proxy` as `campaign-api`; frontend repository's production overlay joins the same network as `campaign-frontend`.
- Caddy serves `FRONTEND_DOMAIN` and `API_DOMAIN`. DNS records must point at the server, and public TCP ports 80/443 must be reachable for automatic certificate provisioning.
- The built-in Caddyfile is a TLS reverse proxy, not a distributed rate limiter; the process-local authentication limits described above are not a substitute for shared limiting on multi-replica deployments.

## Frontend contract
The frontend's routes have been matched against backend route families for auth, audiences/contacts, campaigns, dashboard, analytics, and templates. Playwright exercises the end-to-end workflow and saved-template application; backend tests cover template owner isolation and required-field validation.

## Branch review
Branches previously inspected: `main`, `development`, and `chore/startup-docker-support`. Recursive tree/blob comparisons found both non-main branches behind main with zero commits ahead. No branch was blindly merged.

## CI and test verification
- Latest backend run for rate-limit commit `9e08b9ef9a11` passed: https://github.com/faizansaiyed123/marketing-campaign-management-backend/actions/runs/39364698605
- The successful run includes Python compilation, PostgreSQL migrations and migration/model parity, the API test suite (including auth rate-limit regression checks), normal and production Compose validation, Caddyfile validation, API image build, and the check that the image runs as UID 10001.
- The production overlay commit `75eed9091833` also passed its CI run: https://github.com/faizansaiyed123/marketing-campaign-management-backend/actions/runs/39364404197
- The frontend production overlay commit `9b126f0934cd` passed build, production container smoke test, and the full Playwright integration suite: https://github.com/faizansaiyed123/marketing-campaign-management-frontend/actions/runs/39364319938
- No local test/build run is claimed because a usable clone was unavailable.

## Deployment prerequisites and known limits
- No production URL, VPS, DNS/TLS setup, persistent cloud database, or running service has been provisioned/verified.
- For the one-host Docker approach, create the external `campaign_proxy` network; set `ENVIRONMENT=production`, `POSTGRES_USER`, `POSTGRES_DB`, strong random `POSTGRES_PASSWORD`, strong random `JWT_SECRET_KEY`, `FRONTEND_DOMAIN`, `API_DOMAIN`, exact HTTPS `FRONTEND_ORIGIN`, HTTPS `PUBLIC_BASE_URL`, `COOKIE_SECURE=true`, and `COOKIE_NAME=__Host-campaign_session`.
- Start backend with `docker compose -f docker-compose.yml -f docker-compose.production.yml up --build -d`, then frontend with the corresponding overlay and `VITE_API_URL=https://<API_DOMAIN>`.
- Keep PostgreSQL private. Open required public web ports 80/443 for Caddy; maintain off-host database backups.
- Optional SMTP host/credentials/sender identity must be configured and real delivery tested before claiming email delivery works in production.
- For multiple API replicas/workers, configure a shared distributed limiter; the included limiter is intentionally process-local.
- No secrets are stored here.

## Next action
1. Finish setup on a real host and configure actual DNS/TLS/secrets.
2. Deploy API + worker + PostgreSQL/Caddy, then frontend.
3. Run production smoke tests for health, auth, template ownership, audiences, campaign lifecycle, tracking, and SMTP if enabled.
4. Record deployed URLs, tested responses, logs, and any remaining limitations.
