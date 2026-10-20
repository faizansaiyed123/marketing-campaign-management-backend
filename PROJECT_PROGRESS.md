# Project Progress — Marketing Campaign Management Backend

## Status
The backend's production-critical code/configuration gaps identified during deployment preparation have been addressed on `main`, and the full GitHub Actions workflow passed on the code revision below.
- Shared Redis-backed authentication rate limits replace process-local counters.
- Campaign execution now persists queued work and returns HTTP 202; the background worker owns SMTP sending and records delivery state.
- Production startup rejects missing/shared-Redis misconfiguration, weak placeholder secrets, missing SMTP settings, reserved example hosts/senders, and common placeholder SMTP credentials.
- Caddy forwarding and Uvicorn trusted-proxy settings preserve the real client IP for rate limiting behind the included reverse proxy.
- A real Redis integration test checks atomic rolling-window behavior through independent clients.
- This is a code/CI completion checkpoint, not a claim that a live production domain/server/email provider has been deployed.

## Repositories and revisions
- Backend: https://github.com/faizansaiyed123/marketing-campaign-management-backend
- Frontend: https://github.com/faizansaiyed123/marketing-campaign-management-frontend
- Backend code/config revision verified by CI: `1ddeb0025d5ff894af2be62548139bb9066bfa47`.
- Backend CI passed: https://github.com/faizansaiyed123/marketing-campaign-management-backend/actions/runs/39369021510
- Frontend queued-to-complete report-refresh test and production build/integration suite passed: https://github.com/faizansaiyed123/marketing-campaign-management-frontend/actions/runs/39368383616
- Frontend documentation/progress update also passed CI: https://github.com/faizansaiyed123/marketing-campaign-management-frontend/actions/runs/39368625190

## Application capabilities
- FastAPI + SQLAlchemy + PostgreSQL + Alembic, non-root API container, migrations applied before Uvicorn starts.
- Argon2 password hashing and JWT-backed HttpOnly session cookies, aligned cookie deletion, owner-scoped audiences/contacts/templates, campaign authoring/scheduling/execution/reporting, engagement tracking, dashboard and analytics.
- PostgreSQL holds durable campaign runs and delivery records; Redis is used for shared authentication throttling, not as a campaign-job queue.
- The separate worker checks due scheduled campaigns every 15 seconds and processes queued SMTP delivery work. Email sending is no longer performed synchronously in an API request.

## Authentication rate limiting
- Atomic Redis sorted-set/Lua rolling windows shared across API workers/replicas.
- Login: 10 requests per source IP per minute.
- Registration: 5 requests per source IP per hour.
- If Redis is missing or unavailable, authentication fails closed with HTTP 503 instead of silently bypassing rate limits.
- Redis runs as a password-protected private Compose service with a persistent volume and no published host port.
- Caddy replaces client-supplied `X-Forwarded-For`; Uvicorn honors forwarded headers only from `FORWARDED_ALLOW_IPS` (default covers the default Docker bridge range plus loopback). When using a custom network subnet, set the value to the actual trusted proxy subnet and loopback—do not trust arbitrary internet-supplied forwarding headers.
- CI runs the actual Lua rate-limit script against Redis using two independent connections and verifies a request is allowed after the rolling window passes.

## Campaign delivery and SMTP
- The execute API saves the campaign run and delivery rows, then returns HTTP 202 with the queued report.
- The background worker opens the configured SMTP connection, sends queued messages, updates sent/failed delivery state and finishes run/campaign reporting.
- Production startup requires SMTP host/sender values, TLS, and matching username/password values if authentication is configured; common placeholder hostnames, sender domains and credential placeholders are rejected.
- SMTP may be absent only in development/tests, where queued delivery behavior remains explicit and messages are never falsely marked sent.
- Actual provider credentials, sender-domain verification, SPF/DKIM/DMARC, and delivery/inbox acceptance must be verified with a controlled-inbox test after deploying. They are external provider/domain settings and must not be hard-coded into the repository.

## Deployment architecture
- Base Compose starts PostgreSQL, a private Redis service, API and worker.
- Optional `docker-compose.production.yml` adds Caddy with persistent certificate/config volumes and public TCP 80/443 routing.
- Frontend joins the external Docker network `campaign_proxy` as `campaign-frontend`; backend API joins it as `campaign-api`.
- Production values include unique random `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, `REDIS_PASSWORD`, `ENVIRONMENT=production`, HTTPS `FRONTEND_ORIGIN` / `PUBLIC_BASE_URL`, `COOKIE_SECURE=true`, `COOKIE_NAME=__Host-campaign_session`, actual domains, and real SMTP provider settings.
- The README contains the repeatable single-host deployment commands and smoke-test checklist. Never commit the production `.env` files.

## CI coverage
The passing backend workflow validates:
1. Python compilation and dependency installation.
2. PostgreSQL migrations and migration/model parity.
3. API tests against PostgreSQL, including Redis-backed rate-limit behavior, fail-closed handling, production configuration guards, and worker-owned SMTP sending behavior.
4. The Lua rate-limit script against a real Redis service.
5. Base and production Docker Compose configuration.
6. Caddyfile validation, API image build, and non-root runtime identity.

## Branch review
Previously inspected `main`, `development`, and `chore/startup-docker-support` recursively and compared file paths/blob SHAs. Both non-main branches were behind `main` with zero commits ahead at the time of review. No branches were blindly merged.

## Live deployment status
Source changes are committed and CI-tested; a live deployment has not been performed or independently verified. Provisioning still requires a real host, DNS records for actual frontend/API domains, host firewall/port access, generated production secrets, and SMTP credentials for a verified sender. These values cannot be safely invented or committed in the repository.

## Deployment smoke test
After supplying actual production values and starting the backend then frontend stacks:
1. Confirm `https://<API_DOMAIN>/health` and the frontend open over HTTPS.
2. Verify registration, login, session persistence, logout, and owner isolation for templates/audiences.
3. Execute a campaign and confirm it first appears queued, then changes to sent/failed when the worker processes it.
4. Send a controlled-inbox email and verify report, tracking, and analytics.
5. Verify PostgreSQL backups are copied off-host and can be restored.
