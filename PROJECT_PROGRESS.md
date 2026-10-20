# Project Progress — Marketing Campaign Management Backend

## Status — October 20, 2026
The backend main branch now includes the production-readiness work and a working developer launcher whose service list matches the current Compose stack.
- Distributed authentication rate limits use atomic Redis Lua rolling windows, are shared across workers/replicas, and fail closed when Redis is unavailable.
- The health endpoint checks PostgreSQL and the shared Redis limiter in production; it returns 503 when either required service is unhealthy.
- Cookie-authenticated mutations reject foreign Origin and cross-site Fetch Metadata requests, alongside credentialed CORS.
- Production configuration validates database/JWT/Redis credentials, HTTPS origins, the secure __Host- cookie policy, SMTP sender syntax/placeholder checks, and mutually exclusive certificate-verified STARTTLS/implicit TLS modes.
- Full-stack Caddy and API-only Caddy production overlays require production configuration before startup. The API-only overlay is for an existing Vercel frontend; the full overlay serves both frontend and backend in Docker.
- Campaign execution persists queued delivery records and returns HTTP 202. A separate worker sends campaign messages, supports contact merge fields, preserves links/unsubscribe information in HTML and plain text, and records SMTP refusal/failure outcomes.
- Click tracking only redirects to links that actually exist in the specific personalized campaign delivery; unlisted destinations are rejected.
- Backup/restore scripts validate PostgreSQL archives, protect dump file permissions, support retention/off-host copy, and restore into a separate database.
- The developer launcher python run.py now accurately describes PostgreSQL + Redis + API + worker; CI compiles the launcher as well as the app/tests.
- Both production Compose routes and both Caddy files have CI validation. No live deployment is claimed.

## Repositories and verification
- Backend: https://github.com/faizansaiyed123/marketing-campaign-management-backend
- Frontend: https://github.com/faizansaiyed123/marketing-campaign-management-frontend
- Backend code/config revision verified by passing CI before this documentation-only update: 902ed0b8389c79c4e9bd1ee55b5b7db1bf522521.
- Backend CI: https://github.com/faizansaiyed123/marketing-campaign-management-backend/actions/runs/39379182626
- Frontend Vercel build-guard and integration CI: https://github.com/faizansaiyed123/marketing-campaign-management-frontend/actions/runs/39378747582
- Frontend progress/Vercel documentation CI: https://github.com/faizansaiyed123/marketing-campaign-management-frontend/actions/runs/39378962904
- Backend CI runs Python compilation including run.py, script syntax checks, PostgreSQL migrations and model parity, PostgreSQL-backed API tests, a real Redis rate-limit integration test, complete/incomplete validation for both production Compose overlays, both Caddyfile validations, API Docker image build, and non-root runtime verification.

## Application and delivery behavior
- FastAPI, SQLAlchemy, PostgreSQL, Alembic, Argon2 password hashing, JWT-backed HttpOnly session cookie, owner-isolated audiences/contacts/templates/campaigns, reports, tracking and analytics.
- PostgreSQL stores durable campaign runs/deliveries. Redis is used for shared authentication limits, not as the campaign queue.
- The scheduler/SMTP worker polls every 15 seconds, finds due campaigns, and processes queued runs.
- Supported merge fields: {{first_name}}, {{last_name}}, {{full_name}}, and {{email}}. Substitutions in HTML are escaped and subject control characters are stripped.
- Both email alternatives retain tracked link destinations and an unsubscribe URL. The app recognizes SMTP recipient refusals and connection/send exceptions as delivery failures instead of reporting those emails as sent.
- Open and click events are stored; clicks can only redirect to a target present in the recipient's campaign content. Unsubscribe uses a confirmation flow and supports one-click POST.

## Production security/configuration
- Login: 10 attempts per source IP per minute. Registration: 5 per source IP per hour.
- Redis is private/password-protected and is not published to the host.
- Caddy overwrites X-Forwarded-For; Uvicorn trusts only Caddy's fixed IP 172.30.240.2 and loopback by default. If the private network changes, update the Caddy static address and FORWARDED_ALLOW_IPS together.
- Production Compose refuses missing database/Redis/JWT/origin/domain/SMTP settings; runtime validation rejects obvious placeholders, insecure origins, malformed sender addresses, and invalid SMTP TLS combinations.
- Keep real secrets in untracked deployment .env files. Actual SMTP provider authentication, sender verification and inbox delivery require a controlled-inbox send after deployment; no credentials are invented or committed.

## Deployment options
1. All-Docker frontend and backend: docker-compose.production.yml plus Caddyfile.
2. Existing Vercel frontend, VPS backend: docker-compose.api-production.yml plus Caddyfile.api-only.
- Vercel uses the frontend repository's vercel.json and npm run build:vercel; the production build refuses missing, insecure, localhost, or reserved example API URLs.
- The API-only stack uses the same public API subdomain and cookie/security config. Use a custom frontend HTTPS subdomain and API HTTPS sibling under the same registrable domain.
- The shared Docker network example uses 172.30.240.0/24, gateway 172.30.240.1, and Caddy IP 172.30.240.2; choose an unused subnet that doesn't overlap a LAN/VPN.
- README deployment commands and post-deploy smoke checks are available. Production .env files must never be committed.

## Backups and recovery
- scripts/backup_postgres.sh creates a custom-format PostgreSQL dump, verifies the archive, restricts local permissions, prunes retention, and optionally copies through rclone.
- scripts/restore_postgres.sh validates an archive and restores to a separate database; it refuses to overwrite the configured live database.
- Script syntax and mocked safe-workflow tests pass. A real deployment still needs an actual off-host backup and restore test before its recoverability can be considered proven.

## Branch review
Previously compared main, development, and chore/startup-docker-support recursively. At that checkpoint both non-main branches were behind main with zero commits ahead. No unrelated branches were merged wholesale.

## Live deployment status
The latest source code, database migrations, API tests, container build, production Compose configurations and Caddy configurations are CI-verified. No live production deployment or real email delivery was performed in this session. Going live still needs actual DNS/custom domains, a Linux host with public TCP 80/443, production-only secrets, a verified SMTP provider/sender, a controlled-inbox send, and a tested backup restore. The Vercel dashboard project itself is not accessible through the repository connection, so its domain and environment variable must be confirmed in the existing dashboard.
