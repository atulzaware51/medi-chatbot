# Medibot Project Audit

Audit date: 2026-11-06

## Scope and validation

Reviewed the current backend, frontend, tests, configuration, migration,
deployment files, and documentation. The local `.env`, private documents, and
database contents were not opened. No live service or external penetration
test was used. The existing worktree had substantial user changes and
deletions; those were preserved.

| Check | Result |
|---|---|
| Backend test suite | 77 passed; one LangChain Community deprecation warning |
| Frontend lint | Passed |
| Frontend component tests | 6 passed |
| Frontend production build | Passed |
| `pip check` | No broken installed requirements |
| `pip-audit -r requirements-prod.txt` | No known vulnerabilities after updating `pypdf` |
| `npm audit --omit=dev` | 0 production vulnerabilities |
| Docker image build | Not run successfully; Docker Desktop Linux engine is unavailable |
| PostgreSQL/Render deployment and restore | Not performed |

## Current architecture

- React/Vite frontend is served by FastAPI from `frontend/dist`; Vite proxies
  API requests locally.
- FastAPI accounts and conversations use SQLAlchemy. The Render configuration
  connects to PostgreSQL; local development defaults to SQLite.
- Conversations are server-generated and owner-scoped. The stateless
  LangGraph workflow receives only history loaded after the ownership check.
- Account sessions store hashes of opaque session and CSRF tokens. Session
  cookies are HttpOnly and SameSite=Strict; state-changing authenticated
  requests require the matching CSRF header.
- Conversation inactivity retention defaults to 30 days (configurable from
  1–365), with user-initiated conversation/account deletion. Each conversation
  is capped at 100 messages.
- Authentication, chat, and admin login use database-backed rate limiting.
- Admin remote access is disabled by default. PDF/TXT resources and the FAISS
  index remain filesystem state and require the configured persistent disk.
- A Render Blueprint, Dockerfile, Alembic migration, production dependency
  lock, and GitHub Actions CI workflow are present. They have not been
  verified against a live Render/PostgreSQL environment.

## Findings and remaining risks

1. **High — no account recovery or email verification.** Users can register
   with an email address but cannot verify ownership or recover a forgotten
   password. This limits support and creates account-abuse/operational risks
   for public signup.
2. **High — deployment/recovery has not been validated.** The container build
   could not run locally, and PostgreSQL migration, concurrent rate limiting,
   persistent-disk behavior, and backup restoration have not been tested on
   the target host. Do not treat the Blueprint as a completed deployment.
3. **High — no clinical or privacy validation.** Emergency matching and
   personal medical decision refusals are limited software rules. The
   application is not clinically validated and must not be used for
   diagnosis, treatment, or real patient data.
4. **Medium — remote admin is intentionally disabled.** Enabling it requires
   a unique secret/password and a separately reviewed trusted access-control
   layer. The app's rate limit does not replace that layer.
5. **Medium — frontend development dependency advisories remain.** The
   production Python and npm dependency scans report no known vulnerabilities.
   The full npm audit currently reports four moderate `minimatch` advisories
   in the ESLint 10 dependency chain. A non-breaking `npm audit fix` did not
   clear them. npm's proposed ESLint 9 downgrade is marked unsupported/
   deprecated, so it was not adopted; keep ESLint 10 and monitor for a
   supported upstream fix.
6. **Medium — operational controls are incomplete.** No restore exercise,
   production alerting/monitoring, or verified retention behavior under
   PostgreSQL outages has been completed.

## Implemented controls

- Removed preset admin credentials from `.env.example`.
- Added Argon2id password hashing, opaque hashed database sessions, session
  expiry/revocation, CSRF validation, and generic login failure responses.
- Added owner-filtered conversation operations, account/conversation
  deletion, inactivity cleanup, per-conversation message caps, and tests for
  cross-account access denial.
- Added database-backed login/chat/admin throttling and readiness checks.
- Added Alembic migration, pinned Python locks, Docker/Render configuration,
  frontend component tests, and CI checks.
- Added medical-request refusal behavior and safety regression tests; this is
  not clinical validation.

## Release status

The code implements account-scoped multi-user chat, but the project is **not
yet ready for public or real-health-data use**. Docker, PostgreSQL, Render,
backups/restoration, dependency advisories, account recovery/abuse handling,
and clinical/legal/privacy review remain outstanding. Automated tests and
source review do not establish security certification, regulatory compliance,
or medical safety.

See [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md),
[SECURITY_AUDIT.md](./SECURITY_AUDIT.md), and [README.md](./README.md).
