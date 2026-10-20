# Project Progress — Marketing Campaign Management Backend

## Status — October 20, 2026
Production-readiness work is committed on main. The current backend code and regression tests passed CI at revision `5dd96f80e4c57ec26ba9bca24bedfe9c1488107d`.
- Shared authentication rate limits use atomic Redis rolling windows; missing/unavailable Redis fails authentication closed, and production readiness checks both PostgreSQL and Redis.
- Cookie-authenticated mutations reject foreign Origin requests and cross-site Fetch Metadata requests; CORS is credentialed and limited to the configured frontend origin.
- Production settings validate database/JWT/Redis passwords, HTTPS origins, secure __Host- cookie settings, SMTP sender syntax and verified TLS mode.
- Both full-stack and API-only Compose overlays require production configuration before starting; Caddy handles HTTPS, Uvicorn trusts only the configured proxy IP, and both overlays derive `PUBLIC_BASE_URL` from `API_DOMAIN` so generated tracking/unsubscribe links match the actual API host.
- Campaign execution writes durable deliveries and returns HTTP 202. The worker handles sending asynchronously.
- The worker rechecks subscription status under a row lock immediately before sending. Contacts unsubscribed after queueing are marked skipped; reports show skipped distinct from sent/failed.
- Scheduled campaigns are claimed only if their database state is still scheduled and due at claim time, preventing stale scheduler selections from executing campaigns the user has edited back to draft.
- Campaign reports aggregate counts in PostgreSQL rather than loading all delivery rows into Python. Totals are cumulative across attempts/retries; latest_run_status describes the newest run.
- Supported merge fields: {{first_name}}, {{last_name}}, {{full_name}}, and {{email}}. HTML values are escaped, subject values are sanitized, and both plain-text and HTML messages preserve tracked links/unsubscribe details.
- SMTP recipient refusal is recorded as failed; a contact unsubscribed before send is skipped.
- Click tracking only redirects to destinations present in the personalized campaign body.
- PostgreSQL backup/restore scripts validate archives, protect local permissions, support optional off-host rclone copies, and restore into a new database without overwriting live data.
- run.py accurately describes PostgreSQL + Redis + API + worker.

## Repositories and CI
- Backend: https://github.com/faizansaiyed123/marketing-campaign-management-backend
- Frontend: https://github.com/faizansaiyed123/marketing-campaign-management-frontend
- Backend application code verified by CI before this docs update: c9cf66a409bfb7faa07b7832585b73f5f0b78f11
- Backend code CI: https://github.com/faizansaiyed123/marketing-campaign-management-backend/actions/runs/39401297680
- CI covers Python compilation, shell syntax and mocked backup/restore control-flow tests, PostgreSQL migrations and model parity, API tests against PostgreSQL, real Redis rate-limit integration, both production Compose variants including derived tracking URL checks, both Caddyfiles, Docker image build, and non-root API runtime.

## Delivery and report semantics
- Each execution creates a durable run and one delivery row per subscribed recipient captured during queueing.
- The worker checks each recipient's current subscription status under a row lock immediately before SMTP send. If unsubscribed meanwhile, delivery status becomes skipped and is not sent.
- Delivery summary totals cover attempts across all campaign runs; retries add delivery records. Successful prior recipients are not resent on retry; only failed recipients are retried. latest_run_status reflects only the newest run.
- Campaign aggregate reporting uses SQL GROUP BY counts for statuses/events to avoid loading large delivery histories into API memory.
- SMTP stays optional in development; such work remains queued. Production requires real SMTP credentials/verified sender and TLS configuration. CI uses fake SMTP and cannot validate a real provider or inbox placement.

## Security and production configuration
- Login: 10 requests per source IP per minute; registration: 5 per source IP per hour.
- Redis has password authentication, no published host port and durable Compose storage.
- Production readiness fails if PostgreSQL/Redis required by the API are unavailable.
- Caddy replaces X-Forwarded-For and Uvicorn trusts only Caddy's fixed private IP and loopback by default.
- API mutating requests reject foreign browser Origin and cross-site Fetch Metadata when Origin is absent.
- Keep real secrets in the untracked server .env; never commit production credentials.
- Full-stack Caddy and API-only Caddy are mutually exclusive on a single host because both publish TCP 80/443. The API-only route is for a Vercel-served frontend.

## Backups and recovery
- `scripts/backup_postgres.sh` creates/verifies custom-format dumps with owner-only file mode, retention, and optional off-host copies through rclone. Encryption depends on configuring an rclone crypt remote or another client-side encrypted destination.
- scripts/restore_postgres.sh validates and restores into a separate database, and refuses to overwrite the configured live database.
- CI runs `tests/test_operations.sh` with a fake Docker executable to verify successful backup creation/validation and restrictive permissions, empty-dump rejection, refusal to restore over the configured live database, restore to a separate target, and handling a failed restore. This validates script control flow; a real production archive still must be restored in a controlled environment to prove recoverability.

## Branch review
Previously compared main, development and chore/startup-docker-support recursively. At that checkpoint both non-main branches were behind main with zero commits ahead. No branches were merged wholesale.

## Live deployment status
Code and deployment configurations are CI-tested, but no live production host/domain or real SMTP delivery was accessed or verified. Actual launch still requires the server, real DNS/domains, secure production secrets, valid SMTP provider credentials/verified sender, a controlled-inbox send, and a real backup/restore smoke test. No placeholder resource is being represented as live.
