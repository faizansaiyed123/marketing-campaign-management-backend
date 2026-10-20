# Project Progress — Marketing Campaign Management Backend

## Status
The backend's application, delivery, rate-limiting, tracking, and deployment configuration changes are committed on `main`. The latest full backend CI passed against the code/configuration revision below.
- Redis-backed, atomic authentication rate limits are shared across API workers/replicas.
- Campaign execution queues durable work and returns HTTP 202; background workers send SMTP messages and update delivery state.
- Campaign subject/body personalization is implemented for `{{first_name}}`, `{{last_name}}`, `{{full_name}}`, and `{{email}}`; inserted contact values are escaped in HTML.
- SMTP recipient-refusal responses are recorded as failed deliveries; they are no longer falsely counted as sent.
- Click tracking only redirects to absolute HTTP(S) links actually included in that delivery's personalized campaign content, preventing arbitrary redirect destinations.
- Forwarded headers are trusted only from Caddy's fixed private-network IP, not a broad Docker subnet.
- These changes are CI-verified. A real production deployment still requires a server, actual domains/DNS, secrets, and working SMTP provider credentials; no live service is claimed.

## Repository and verification
- Backend: https://github.com/faizansaiyed123/marketing-campaign-management-backend
- Frontend: https://github.com/faizansaiyed123/marketing-campaign-management-frontend
- Backend code/configuration revision passed by CI: `6a7626417bf0a748113ef03c10519dd22a845c5c`.
- Backend CI: https://github.com/faizansaiyed123/marketing-campaign-management-backend/actions/runs/39371232405
- Frontend campaign-report refresh and personalization-help UI CI: https://github.com/faizansaiyed123/marketing-campaign-management-frontend/actions/runs/39370945582
- CI covers Python compilation, PostgreSQL migration execution/parity, PostgreSQL-backed API tests, a real Redis rate-limit test, Compose configuration, Caddy validation, Docker image build, and non-root runtime identity.
- Frontend CI covers the Vite production build/container smoke test and full Playwright API integration suite.

## Application capabilities
- FastAPI + SQLAlchemy + PostgreSQL + Alembic; API container runs as non-root and applies migrations before serving.
- Argon2 password hashing and JWT-backed HttpOnly session cookies, strict production checks, owner-scoped audiences/contacts/templates, campaign authoring/scheduling/reporting, tracking, dashboard and analytics.
- PostgreSQL stores durable campaign runs and delivery rows. Redis is used for shared authentication rate limits, not as the campaign queue.
- The separate worker polls every 15 seconds, queues due campaigns, sends queued SMTP messages, and persists sent/failed outcomes.

## Authentication rate limiting
- Atomic Redis sorted-set/Lua rolling windows shared across API workers/replicas.
- Login: 10 requests per source IP per minute.
- Registration: 5 requests per source IP per hour.
- Missing or unavailable Redis fails authentication closed with HTTP 503.
- Redis is a password-protected, private Compose service and its port is not published to the host.
- The production overlay gives Caddy fixed IP `172.30.240.2` on `campaign_proxy`; Uvicorn trusts only `172.30.240.2,127.0.0.1` by default. Caddy overwrites `X-Forwarded-For` with the remote client address. If you change the proxy-network subnet or Caddy address, update `docker-compose.production.yml` and `FORWARDED_ALLOW_IPS` together.

## Campaign delivery, personalization and tracking
- The execute API persists queued work and returns HTTP 202; it does not send mail while holding an HTTP request open.
- Supported merge fields are `{{first_name}}`, `{{last_name}}`, `{{full_name}}`, and `{{email}}`. HTML substitutions are escaped, and subject substitutions strip line/control characters to avoid header injection.
- SMTP refusal mappings and connection/send exceptions are recorded as failed deliveries; successful SMTP acceptance updates sent status. Real provider acceptance and inbox delivery still require a controlled-inbox test.
- Unsubscribes are explicit-confirmation links, and the one-click unsubscribe header uses the POST endpoint.
- Click-tracking redirects are limited to links in that specific personalized campaign body; unlisted external targets are rejected with HTTP 400.

## Deployment architecture
- Base Compose starts PostgreSQL, password-protected Redis, API and worker.
- Optional `docker-compose.production.yml` adds Caddy for automatic HTTPS and domain routing, with persistent certificate storage.
- Frontend joins external network `campaign_proxy` as `campaign-frontend`; API/Caddy join it as `campaign-api`/Caddy proxy.
- Create the shared bridge network with an unused private subnet before bringing up either stack. The documented example uses `172.30.240.0/24`, gateway `172.30.240.1`, and static Caddy address `172.30.240.2`.
- Production values include unique random database/JWT/Redis secrets, `ENVIRONMENT=production`, HTTPS `FRONTEND_ORIGIN` and `PUBLIC_BASE_URL`, `COOKIE_SECURE=true`, `COOKIE_NAME=__Host-campaign_session`, real frontend/API domains, and real SMTP settings.
- The README contains commands and a deployment smoke-test list; never commit real `.env` files.

## Branch review
Previously inspected `main`, `development`, and `chore/startup-docker-support` recursively and compared file paths/blob SHAs. At the time of review both non-main branches were behind main with zero commits ahead. No branches were blindly merged.

## Live deployment status
The code and container/deployment definitions are CI-tested, but a live production deployment has not been performed or verified. Actual launch requires a Linux host, DNS pointing the real domains to that host, inbound web ports 80/443, private production secrets, and valid SMTP-provider credentials/sender authorization. Those external credentials and domain details are unavailable here and must not be fabricated or committed.

## Deployment smoke checks
After configured stacks are started:
1. Confirm API health and frontend load over HTTPS.
2. Test registration, login, session persistence, logout, and owner isolation for audiences/templates.
3. Send a campaign with merge fields; verify the delivered subject/body uses contact values.
4. Confirm queued deliveries become sent or failed, including provider-recipient refusals.
5. Test open/click tracking, rejection of unlisted redirect targets, unsubscribe, and analytics.
6. Verify off-host PostgreSQL backups and a restore procedure.
