# Medibot

Medibot is an educational, document-grounded medical information chatbot built
with React, FastAPI, LangGraph, Sentence Transformers, and FAISS. It retrieves
passages from administrator-provided PDF/TXT resources and returns answers with
source references where available.

Medibot is not a diagnostic system, has not been medically validated, and does
not replace a qualified healthcare professional. Do not use it for emergencies
or personalized treatment decisions.

## Features

- React/Vite chat UI with source references and an educational disclaimer.
- PDF/TXT upload and FAISS indexing through admin resources dashboard.
- Retrieval-grounded responses with limited deterministic safety handling.
- Account registration/login, server-generated conversation IDs, and
  owner-scoped server-side conversation history.
- 30-day default inactivity retention, user-initiated conversation/account
  deletion, and database-backed rate limiting.
- Loopback-only admin resource access by default.

## Architecture

```text
React/Vite
    | /api
FastAPI
    +-- SQLAlchemy account/session/conversation database
    +-- Stateless LangGraph answer workflow
    +-- FAISS retrieval <--- PDF/TXT ingestion
    +-- Configured hosted LLM
```

PDF/TXT resources are uploaded through admin endpoints, split into
chunks, embedded locally, and used to build the FAISS index. The chat flow
uses the configured Groq model only when the safety and evidence checks allow
it; selected emergency and personal diagnosis/medication decision responses
are deterministic. Explicit conversation history is read from the authenticated
owner's database records and passed to the workflow.

## Privacy and deployment limits

Conversation history is account-scoped and stored in the configured
application database; the browser does not persist transcripts in
`localStorage`. Conversations inactive for 30 days are deleted by default
(configurable from 1 to 365 days). Sessions expire after seven days.
Registration has no email verification or password-recovery flow. Do not enter
personally identifying or sensitive health information: this service is
educational, has not been medically validated, and is not suitable for
clinical decisions.

The Render configuration uses PostgreSQL for account/chat data and one
persistent disk for uploaded documents and the FAISS index. The admin remote
override is disabled by default; do not enable it without an additional
trusted access-control layer.

## Requirements and local setup

- Python 3.12 (the existing local virtual environment is Python 3.12).
- Node.js and npm.
- A configured supported LLM provider key/model and local embedding model.

Create a local `.env` from `.env.example`, then set the provider credentials and
model name. Never commit `.env`.

Install backend dependencies if creating a new environment:

```powershell
python -m pip install -r requirements.txt
```

Start FastAPI from the project root:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The migration imports accounts and conversation history from the previous
`MEDIBOT_AUTH_DB_PATH` SQLite database (default
`data/medibot_auth.sqlite3`) when present. Existing users keep their accounts
and password hashes but must sign in again. If the legacy database is separate
from the configured application database, its file is left intact; remove it
after verifying the migrated data. If both settings point to the same SQLite
file, its schema is upgraded in place and old sessions are invalidated.

In another terminal:

```powershell
Set-Location .\frontend
npm install
npm run dev -- --host 127.0.0.1
```

Open the local URL printed by Vite. Its `/api` proxy forwards requests to
FastAPI at `127.0.0.1:8000`.

## API Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/register` | Create an account and sign in |
| POST | `/auth/login` | Sign in |
| GET | `/auth/me` | Get current account/session state |
| POST | `/auth/logout` | Revoke the current session |
| DELETE | `/auth/me` | Delete the account and its conversations |
| POST | `/chat/conversations` | Create a server-owned conversation |
| GET | `/chat/conversations` | List the signed-in user's conversations |
| GET | `/chat/conversations/{id}` | Restore an owned conversation |
| POST | `/chat/conversations/{id}/messages` | Ask a question in that conversation |
| DELETE | `/chat/conversations/{id}` | Delete an owned conversation |
| GET | `/admin/resources/auth/status` | Check admin access and whether login is required |
| POST | `/admin/resources/auth/login` | Sign in with the configured admin password |
| POST | `/admin/resources/auth/logout` | Clear the admin session cookie |
| GET | `/admin/resources/` | List uploaded resources and index status |
| POST | `/admin/resources/upload` | Upload and index a PDF or TXT resource |
| GET | `/health` | Process liveness |
| GET | `/ready` | Database readiness |

Unsafe account and conversation operations require the session-bound
`X-CSRF-Token` returned by the authentication endpoints. Session and CSRF
cookies are `SameSite=Strict`; the session cookie is HttpOnly.

## Admin access and network safety

Keep `MEDIBOT_ADMIN_LOCAL_DEV` and `MEDIBOT_ADMIN_ALLOW_REMOTE` false in
deployed environments unless an explicitly reviewed access-control design
requires otherwise. Remote admin sessions are rate-limited and use a signed
HttpOnly, SameSite=Strict cookie. Set a unique
`MEDIBOT_ADMIN_PASSWORD` and `MEDIBOT_ADMIN_SESSION_SECRET` only in the host's
secret settings if admin login is intentionally enabled. Never use example or
reused credentials.

## Documents and evaluation

Admin accepts PDF and TXT documents up to 20 MiB, validates readable content,
and stages FAISS index rebuilds before replacing the active index. Uploaded
documents and the index are local application data. Only upload resources you
are authorized to use and review them for accuracy and suitability.

The `evaluation/` directory contains preliminary evaluation scripts and
artifacts. They are not a validated medical benchmark and do not establish
clinical safety. Versioned datasets, reproducible run tracking, comprehensive
retrieval/grounding/safety metrics, and qualified clinical review remain
incomplete.

## Testing

Run backend tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Run frontend checks and component tests:

```powershell
Set-Location .\frontend
npm run lint
npm run test
npm run build
```

Pytest uses a disposable application database. The production-only Python
dependency lock is `requirements-prod.txt`; `requirements.txt` includes the
test dependencies.

## Hosting on Render (not yet deployed)

`render.yaml` defines a Docker web service, PostgreSQL database, and persistent
disk. The service is public unless you add an external access gate. It is
single-instance because the uploaded resources and FAISS index live on one
disk. The configuration is not a live deployment; verify current Render
Blueprint requirements and costs before provisioning.

1. Review the complete worktree and push the source to a GitHub repository.
   Never commit `.env`, API keys, database files, uploaded private documents,
   or FAISS indexes.
2. In Render, create a **Blueprint** from the repository so it reads
   `render.yaml`. This provisions a paid web service, PostgreSQL, and a
   persistent disk; confirm current plan availability and charges first.
3. In the Render service settings, set `GROQ_API_KEY` as a secret and
   `GROQ_MODEL` to a model available to your provider account. Keep
   `MEDIBOT_COOKIE_SECURE=true`, and do not set admin remote access flags to
   true.
4. Deploy. The configured pre-deploy command runs database migrations; the
   service uses `/ready` for database readiness and `/health` for liveness.
   Visit `https://<your-service>.onrender.com`, create an account, and test
   conversation creation, restore, deletion, sign-out, and a redeploy.
5. Back up the PostgreSQL database and persistent disk independently, then
   perform a restore test before storing anything important. Render does not
   replace an application-specific recovery plan.

Do not treat deployment as evidence of clinical validation, regulatory
compliance, or security certification. Never store real patient information
until suitable privacy, legal, clinical, operational, and security reviews
have been completed.

## Known limitations and deployment status

- There is no email verification or password recovery; public registration
  needs an account-abuse and support plan.
- PostgreSQL migrations and a Render Blueprint are configured but have not
  been validated against a live Render service. No backup/restore test or
  PostgreSQL integration test has been performed.
- Dockerfile/container build has not been verified because the local Docker
  engine was unavailable.
- Medical emergency recognition and personal medical decision refusals are
  limited logic, not clinical advice or a substitute for emergency services.
- Evaluation remains preliminary, and no qualified clinical/legal review has
  occurred.
- The service has not been deployed.

See [PROJECT_AUDIT.md](./PROJECT_AUDIT.md),
[IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md), and
[SECURITY_AUDIT.md](./SECURITY_AUDIT.md) for audited status and next steps.
