# Project Progress — Marketing Campaign Management Backend

## Status — October 20, 2026
The backend production-readiness changes are committed on `main`; the current application changes and PostgreSQL schema migration passed CI.
- Authentication rate limits are atomic Redis Lua rolling windows shared across API workers/replicas; missing Redis fails closed, and production readiness checks PostgreSQL plus Redis.
- Cookie-authenticated mutations reject foreign Origin/cross-site Fetch Metadata requests, alongside credentialed CORS.
- Production startup validates strong DB/JWT/Redis settings, HTTPS origins, secure `__Host-` cookies, SMTP sender syntax and certificate-verified TLS settings. Both Docker deployment overlays require production config before startup.
- Campaign execution persists durable delivery rows and returns HTTP 202. The worker sends through SMTP, handles refused recipients accurately, and safely records sent/failed state.
- The worker rechecks each contact's subscription state under a database row lock immediately before sending. A contact who unsubscribes after the campaign is queued but before the send is skipped—not sent or counted as an SMTP failure.
- Campaign delivery summaries expose skipped counts; Alembic migration `0004_delivery_skipped_count` stores the per-run skipped total.
- Merge fields `{{first_name}}`, `{{last_name}}`, `{{full_name}}`, and `{{email}}` are escaped into HTML and sanitized for email subjects. Plain-text and HTML alternatives include tracked links/unsubscribe instructions.
- Click tracking only redirects to URLs actually included in the personalized campaign body.
- PostgreSQL backup/restore scripts validate archives and restore to a separate database; off-host copying is supported with rclone.
- The developer launcher reports the actual Compose services: PostgreSQL, Redis, API, and worker.

## Repositories and verification
- Backend: https://github.com/faizansaiyed123/marketing-campaign-management-backend
- Frontend: https://github.com/faizansaiyed123/marketing-campaign-management-frontend
- Backend application/schema revision verified by CI: `99358fc3b282354ac586f536d458134ad0e30eff`.
- Backend CI run for that revision: https://github.com/faizansaiyed123/marketing-campaign-management-backend/actions/runs/39386023991
- Frontend unsubscribe/report UI integration CI: https://github.com/faizansaiyed123/marketing-campaign-management-frontend/actions/runs/39386307829
- Backend CI includes Python compilation, operational-script syntax, PostgreSQL migration and model parity checks, PostgreSQL-backed API tests, real Redis rate-limit tests, production Compose validation, both Caddyfile validations, API image build, and non-root runtime verification.

## Application and delivery design
- FastAPI, SQLAlchemy, PostgreSQL, Alembic, Argon2 password hashes, JWT-backed HttpOnly session cookie, owner-isolated users/audiences/contacts/templates/campaigns, tracking and analytics.
- PostgreSQL stores campaign runs and delivery attempts; Redis is shared rate-limit storage, not a campaign queue.
- The worker checks scheduled campaigns every 15 seconds and uses row locks to coordinate delivery processing.
- Report counts are campaign-wide delivery-attempt totals across retries; `latest_run_status` separately describes the most recent run.
- Skipped contacts are displayed separately from sent/failed messages. Retry runs only retry failed deliveries and do not re-send contacts already successfully sent.
- A genuine SMTP provider/account/verified sender and controlled-inbox test are still required to verify external email delivery. CI uses a fake SMTP server by design.

## Production security
- Login limit: 10 requests per source IP per minute; registration limit: 5 per IP per hour.
- Redis is private and password-protected, with no published host port.
- Caddy overwrites `X-Forwarded-For`; Uvicorn trusts only Caddy's fixed private IP `172.30.240.2` and loopback by default.
- Production env files are untracked; no secrets are committed. Full-stack Caddy and Vercel-frontend/API-only Caddy are separate deployment choices and must not both publish host ports 80/443 on the same server.
- Keep the API and frontend on HTTPS custom subdomains under the same registrable domain for the strict session cookie; set the exact frontend origin in backend configuration.
- `docker-compose.production.yml` serves frontend + API on one server; `docker-compose.api-production.yml` serves API only for an existing Vercel frontend.

## Backups and live deployment
- `scripts/backup_postgres.sh` produces a verified custom-format dump with owner-only file permissions and retention; it can copy to an off-host remote.
- `scripts/restore_postgres.sh` validates and restores into a separate database, refuses to overwrite the configured live database, and keeps the original unchanged if restore fails.
- Scripts and mocked safe-workflow tests pass CI. A production backup is not proven recoverable until a real archive has successfully been restored.
- Code and deployment configuration are CI-checked; no live production domain, server, SMTP provider, or real inbox delivery was supplied or verified. Actual launch still needs those external resources and post-deployment smoke tests.
