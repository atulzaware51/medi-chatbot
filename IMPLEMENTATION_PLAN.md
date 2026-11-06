# Medibot Implementation Plan

Updated: 2026-11-06

This plan describes the current implementation and remaining release work.
The repository worktree contained pre-existing user changes; those changes
were preserved. Review the complete diff before staging or publishing.

## Phase 0: Audit and baseline — complete

- [x] Review backend, frontend, tests, configuration, and deployment material.
- [x] Record audit findings and deployment limitations.

## Phase 1: API and configuration fixes — complete

- [x] Remove the example admin password and unsupported provider settings.
- [x] Reject whitespace-only chat input at the API boundary.
- [x] Return generic server errors while logging server-side failures.
- [x] Correct stale deployment and privacy documentation.

## Phase 2: Multi-user privacy and access control — implemented

- [x] Add account registration/login with Argon2id password hashing and
  revocable, expiring, opaque database sessions.
- [x] Use HttpOnly/SameSite cookies and session-bound CSRF checks for
  state-changing account and conversation requests.
- [x] Generate conversation identifiers on the server and enforce owner
  checks for listing, reading, messaging, and deletion.
- [x] Store conversation history in the application database, cap each
  conversation at 100 messages, and remove inactive conversations after
  the configurable 1–365 day retention period (30 days by default).
- [x] Add account/conversation deletion, cleanup of expired sessions, and
  database-backed rate limits for authentication, chat, and admin login.
- [x] Add tests for authentication, expiry, CSRF, ownership isolation,
  deletion, rate limits, migrations, and stateless workflow history.

Remaining caveats: there is no email verification or password-recovery
workflow. Public registration still needs abuse/support processes, and the
service must not collect sensitive health data absent appropriate review.

## Phase 3: Repeatable Render deployment — implementation complete, external
verification pending

- [x] Add production and development Python dependency inputs and pinned locks.
- [x] Add Docker build, non-root runtime entrypoint, PostgreSQL migration, and
  `/health` and database-backed `/ready` endpoints.
- [x] Add a Render Blueprint for one web instance, PostgreSQL, and a persistent
  disk; document setup and secret configuration.
- [x] Add GitHub Actions checks for backend tests and frontend lint/tests/build.
- [ ] Build and run the Docker image in an environment with a working Docker
  engine. The local Docker CLI was present, but its Linux engine was not.
- [ ] Validate PostgreSQL migration, concurrency, and backup/restore behavior.
- [ ] Confirm the current Render Blueprint schema, plan availability, and
  pricing; deploy only with the account owner's credentials and approval.
- [x] Add automated production dependency advisory scans to CI. The current
  production Python and npm scans report no known vulnerabilities; moderate
  frontend development-dependency advisories still need review.

The Render configuration is not a deployed service. A single persistent disk
does not support horizontal scaling; keep the service at one instance unless
resource storage is redesigned.

## Phase 4: Medical safety and evaluation — partially implemented

- [x] Add conservative deterministic responses for selected emergency,
  diagnosis, and medication-decision requests and tests for those paths.
- [x] Add preliminary evaluation scripts and example artifacts.
- [ ] Create a versioned, representative synthetic test set and define
  reproducible retrieval, citation support, groundedness, refusal, and answer
  quality measures with explicit denominators and N/A handling.
- [ ] Do not rely on model-judge scores as clinical truth; obtain qualified
  clinical, privacy, and legal review before any real clinical use.

Medical safeguards are limited and not clinically validated. They do not
replace a qualified healthcare professional or emergency services.

## Phase 5: Frontend and operations — partially implemented

- [x] Add frontend component tests and server-backed history/authentication.
- [x] Make inactivity retention and lack of account recovery visible in the UI.
- [ ] Expand UI tests for error, loading, admin, and browser-navigation cases.
- [ ] Add safe operational monitoring that excludes question text, credentials,
  and other sensitive user content.
- [ ] Perform deployment persistence and recovery checks after a real
  environment is provisioned.

## Current validation

- Backend: 77 tests pass.
- Frontend: lint, 6 component tests, and production build pass.
- `pip check`: no broken installed requirements.
- `pip-audit -r requirements-prod.txt`: no known vulnerabilities after
  updating `pypdf`; `npm audit --omit=dev`: 0 production vulnerabilities.
  Full npm audit reports four moderate ESLint-chain advisories; non-breaking
  `npm audit fix` did not resolve them, and npm marks the proposed ESLint 9
  downgrade unsupported/deprecated. The supported ESLint 10 line is retained
  pending an upstream fix.
- Production dependency lock includes the multipart parser needed by admin
  file uploads.
- Docker build was attempted but could not run because Docker Desktop's Linux
  engine was unavailable.
- No live Render deployment, PostgreSQL integration/restore test, qualified
  medical/legal review, or external penetration test has been performed.

## Release gate

Do not describe Medibot as production-ready, medically validated, compliant,
or security-certified. Before public use, complete the remaining deployment,
recovery, account-abuse, dependency-advisory, and clinical/privacy reviews.
Do not accept real patient information until those reviews and applicable
requirements have been addressed.
