# Medibot Security Audit

Review date: 2026-10-31

## Scope

Read-only review of the current application source, tests, and deployment
documentation. `.env`, credentials, and private application data were not
opened. No live deployment, external service, or dependency vulnerability scan
was performed.

## Findings

### HIGH: Chat checkpoint threads have no authenticated ownership

- **Evidence:** [chat.py](./app/api/chat.py) accepts a client-supplied
  `thread_id`; [workflow.py](./app/graph/workflow.py) passes that value to the
  LangGraph checkpointer without binding it to an authenticated user.
- **Impact:** A person who obtains another conversation's thread ID can
  continue that thread and cause the model to receive its saved history. The
  current API has no account identity or authorization boundary.
- **Recommended remediation:** Implement authentication, persist conversation
  ownership, generate thread IDs server-side, and verify ownership on every
  conversation operation. Add cross-user tests before enabling persistent
  conversation history for multiple users.
- **Confidence:** 9/10.

### MEDIUM: Admin routes are not restricted to loopback

- **Evidence:** [admin.py](./app/api/admin.py) checks for a bearer token but
  does not check the ASGI peer address. The existing remote-client test in
  [test_admin_security.py](./tests/test_admin_security.py) explicitly expects
  a remote client with the token to succeed. This conflicts with the
  loopback-only statement in [README.md](./README.md).
- **Impact:** If the service is reachable from another machine and the admin
  token is disclosed, a remote caller can access admin resource operations,
  including uploads and index rebuilding.
- **Recommended remediation:** Until a deliberately designed production admin
  access model exists, bind the backend to loopback for local use and do not
  expose admin routes publicly. For deployment, use authenticated access,
  TLS, and network restrictions appropriate to the hosting environment.
- **Confidence:** 9/10.

## Remediation status

Both findings were addressed in the current worktree:

- The chat API now requires a valid expiring bearer session. Account identity
  comes from the session, not a request-supplied user ID. Conversations are
  created by the server, and chat, message-read, and delete operations verify
  ownership. Conversation messages are persisted; deletion also removes the
  LangGraph checkpoint. Registration/login use Argon2 and have per-IP
  throttling.
- Admin routes now reject non-loopback peers by default. Remote access is
  possible only with the explicit `MEDIBOT_ADMIN_ALLOW_REMOTE=true` setting
  and still requires the admin bearer token. Do not enable the override
  without a production network/TLS access review.

The focused authentication, ownership, and admin tests pass. Remaining
security work includes a production database/migration design, production
deployment/network review, and reducing exposure of the admin token in browser
storage.

## Controls observed

- Admin requests fail closed if `MEDIBOT_ADMIN_TOKEN` is unset, and token
  comparison uses `secrets.compare_digest`.
- Resource upload validates the filename and extension, enforces a size cap,
  stages files before publication, and uses an index replacement/rollback
  workflow.
- Client-facing indexing failures are generic; React renders answer and
  resource text as text rather than injecting raw HTML.
- `.gitignore` excludes `.env`, local databases, raw documents, vector indexes,
  and virtual environments. Continue to verify the staging area before
  publishing.

## Additional notes

- The admin token is also held in browser `sessionStorage`; keep the admin UI
  restricted to trusted users and avoid introducing unsafe HTML rendering.
- Dependency manifests are not pinned, and no dependency vulnerability scan
  was performed.
- A credential-like value was visible in the editor selection during this
  task. If it is active, rotate it; its value was not read from `.env`,
  copied into project files, or included in this report.
- These findings do not establish clinical safety or medical validation.
