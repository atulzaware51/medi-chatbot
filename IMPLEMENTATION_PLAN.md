# Medibot Implementation Plan

This plan follows the existing application and favors small, verifiable
changes over a replacement project. Phases that introduce authentication,
database ownership, and medical safety behavior require focused tests before
deployment.

## Phase 0: Audit and baseline

- [x] Inspect current backend, frontend, tests, manifests, and repository state.
- [x] Run baseline backend tests and frontend build/lint.
- [x] Record findings in `PROJECT_AUDIT.md`.
- [x] Complete `SECURITY_AUDIT.md` from a source-reviewed security assessment.

Baseline: 58 backend tests passed; frontend build passed; lint had one warning
and no errors. No frontend test runner, Render configuration, or root
Dockerfile was found.

## Phase 1: Stabilize current application

- [x] Address concrete defects from the security audit and test them.
- [x] Correct frontend lint warnings and navigation state behavior.
- Keep chat, ingestion, retrieval, and local SQLite use working.
- Add regressions before changing existing API behavior.

## Phase 2: Frontend and navigation

- [ ] Improve responsive and accessible chat/admin presentation.
- [x] Synchronize `/` and `/admin` with browser history.
- Add robust loading, empty, retry, and error states.
- Establish frontend component tests before larger UI additions.

Progress: browser Back/Forward navigation now synchronizes the chat/admin
view, the Chat control returns to `/`, and New chat resets its state without a
full-page reload. Account login/registration, simple history restoration and
deletion are wired to the backend. Frontend lint and production build pass.

## Phase 3: Authentication and conversation history

- [x] Select a secure session/token and password-hashing approach compatible
  with local Windows development.
- [ ] Add production database models and migrations (local SQLite-backed
  users, sessions, conversations, and messages are implemented).
- [x] Enforce identity-derived ownership on conversation operations.
- [x] Persist and restore a distinct LangGraph thread for each owned
  conversation.
- [x] Test invalid credentials, cross-user access, persistence, restoration,
  and deletion.

## Phase 4: RAG and memory

- Preserve staged FAISS replacement and add duplicate/content integrity
  checks, configuration validation, and retrieval tests as needed.
- Keep conversation checkpoints separate from consent-based profile memories.
- Bound context and history supplied to generation.
- Verify citation IDs and evidence behavior with deterministic model mocks.

## Phase 5: Evaluation framework

- Define versioned, clearly synthetic examples pending qualified medical
  review; do not present them as authoritative clinical benchmarks.
- Implement unit-tested retrieval, token-answer, semantic, claim support,
  citation, and safety metrics with explicit N/A and zero-claim behavior.
- Persist run metadata/results and export JSON/CSV.
- Avoid presenting automated model-judge results as ground truth.

## Phase 6: Medical safety and dashboard

- Add a separate, testable conservative safety policy for emergencies,
  medication dosing/changes, diagnosis requests, and other listed scenarios.
- Build an admin-only evaluation dashboard from persisted results, not
  hardcoded values.
- Clearly communicate evidence gaps, uncertainty, source conflicts, and
  educational limitations.

## Phase 7: Security and quality

- Resolve all confirmed security findings and add focused regression tests.
- Add API, isolation, ingestion, safety, and evaluation test coverage.
- Run backend tests, frontend tests/build/lint, and dependency checks.
- Verify no credentials, local data, or private documents are staged.

## Phase 8: GitHub and Render preparation

- Add reproducible compatible dependencies, production configuration, and a
  Render native Python deployment definition.
- Configure PostgreSQL and persistent document/index storage with migrations,
  health checks, and correct `$PORT` binding.
- Document secrets, backups/recovery, deployment, limitations, and safe Git
  publication.
- Report deployment only after a real deployment and health check succeed.

## Release gate

Do not describe the project as production-ready or medically validated until
the requested authentication/ownership, persistent data, evaluation, safety,
deployment, and test acceptance criteria have been implemented and verified.
External services, qualified clinical review, and deployment credentials may
still require explicit user action.
