# Project Progress — Marketing Campaign Management Backend

## Status — October 20, 2026
The backend's production-readiness changes are committed on main. The latest full backend CI passed on the code revision before this progress-file update.
- Redis-backed atomic authentication throttling is shared across API workers/replicas; missing or unavailable Redis fails closed, and readiness returns 503 when it is down.
- Unsafe API mutations reject foreign Origin requests and cross-site Fetch Metadata without Origin, complementing credentialed CORS.
- Production settings validate strong DB/JWT/Redis credentials, HTTPS origins, secure cookie policy, SMTP sender syntax, and mutually exclusive verified STARTTLS/implicit-TLS configuration.
- Full-Docker and API-only production Compose overlays require their production environment values before containers start.
- Campaign execution saves durable delivery work and returns HTTP 202; the worker sends messages, supports personalized fields and text/HTML alternatives, persists SMTP refusals/failures, and completes reporting.
- Tracking redirects only to URLs present in that delivery's personalized campaign body.
- Backup/restore scripts create validated PostgreSQL dumps, apply retention, optionally copy backups off-host with rclone, and restore into a separate database.
- A Vercel frontend deployment path is documented and validated alongside the all-Docker path. No hosting integration was installed or connected.

## Repositories and verification
- Backend: https://github.com/faizansaiyed123/marketing-campaign-management-backend
- Frontend: https://github.com/faizansaiyed123/marketing-campaign-management-frontend
- Backend API/production-config code revision: c7c82903d7afda263bb82607c7b2089709482571
- Backend CI for this revision: https://github.com/faizansaiyed123/marketing-campaign-management-backend/actions/runs/39377923882
- Frontend Vercel config/code revision before its progress update: acf872b67421e802863f2ee4496750b01adae7e5
- Frontend CI for that revision: https://github.com/faizansaiyed123/marketing-campaign-management-frontend/actions/runs/39378045862
- Backend CI checks Python compilation, operational script syntax, PostgreSQL migrations and model parity, PostgreSQL-backed API tests, real Redis rate-limit behavior, both production Compose overlays, both Caddyfiles, API image build, and non-root runtime.

## Application and delivery behavior
- FastAPI, SQLAlchemy, PostgreSQL, Alembic, Argon2 password hashing, JWT-backed HttpOnly session cookie, owner-isolated audiences, contacts, templates and campaigns, reports, engagement tracking, and analytics.
- PostgreSQL stores campaign runs and delivery records; Redis is shared authentication rate-limit storage, not the campaign queue.
- The separate worker polls every 15 seconds and processes due campaigns and queued SMTP deliveries.
- Supported merge fields are {{first_name}}, {{last_name}}, {{full_name}}, and {{email}}. HTML substitutions are escaped; subject substitutions remove control characters.
- Plain-text and HTML email alternatives retain tracked links and unsubscribe information. Recipient refusal responses are recorded as failures rather than falsely shown as sent.
- Open/click events are persisted. Click destinations must be included in the individual personalized campaign body. Unsubscribe requires explicit confirmation in a browser and supports the one-click POST header.

## Production security and configuration
- Login rate limit: 10 requests per source IP per minute. Registration rate limit: 5 per source IP per hour.
- Redis is private/password-protected and has no published host port. Production readiness checks both PostgreSQL and Redis.
- Caddy overwrites X-Forwarded-For; Uvicorn trusts only Caddy's fixed private-network address 172.30.240.2 and loopback by default.
- Production Compose fails early if required DB, Redis, JWT, origin, domain, or SMTP fields are missing. The application also rejects obvious placeholder hosts/senders/secrets and malformed sender addresses.
- SMTP supports either certificate-verified STARTTLS or implicit TLS, never both at once. Real sender verification, provider authentication, DNS email authentication, and inbox delivery are external checks.
- Keep real settings in an untracked server .env; never commit credentials or production secrets.

## Deployment options
1. All-Docker frontend plus backend: use docker-compose.production.yml and Caddyfile.
2. Frontend on the user's existing Vercel project, backend on a VPS: use docker-compose.api-production.yml and Caddyfile.api-only. The frontend and API must use custom HTTPS subdomains under the same registrable domain for the strict session cookie.
- Both options use the external campaign_proxy network sample 172.30.240.0/24, gateway 172.30.240.1, and static Caddy IP 172.30.240.2. Choose an unused private subnet and update the trusted-proxy configuration if changing it.
- Both deployment approaches require actual domains/DNS, a Linux host for the backend, unique production secrets, and valid SMTP provider settings. Vercel previews are not allowed to use the production API by default.
- The README contains deployment commands and smoke tests. No live domain/server/email delivery has been claimed.

## Backups and recovery
- scripts/backup_postgres.sh creates a custom-format PostgreSQL dump, validates it, protects local file permissions, prunes retention, and optionally copies to a remote destination through rclone.
- scripts/restore_postgres.sh validates the dump and restores to a separate database; it refuses to overwrite the configured live database.
- Script syntax and mocked safe-workflow tests pass. A real production restore must still be exercised after deployment before claiming recoverability.

## Branch review
Previously compared main, development, and chore/startup-docker-support recursively. Both non-main branches were behind main with zero commits ahead at that checkpoint. No branches were merged wholesale.

## Live deployment status
The code, migration, integration test, Docker build, and Compose/Caddy configuration have been CI-checked, but no live production deployment has been performed or independently verified. It still needs real domain/DNS, host firewall access on ports 80/443, private production secrets, an SMTP account and verified sender, and successful post-deployment test email and backup restore. No secrets or provider accounts were invented.
