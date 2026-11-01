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
- PDF/TXT upload and FAISS indexing through protected admin endpoints.
- Retrieval-grounded responses, limited deterministic emergency phrase
  handling, and SQLite-backed LangGraph checkpoints.
- Argon2 password hashing and opaque, expiring bearer sessions.
- Authenticated user accounts with conversation ownership, persisted messages,
  history restoration, and user-requested conversation deletion.
- Loopback-only admin resource access by default.

## Architecture

```text
React/Vite
    | /api
FastAPI
    +-- Authentication and conversation/message storage (SQLite)
    +-- LangGraph workflow and checkpoints (SQLite)
    +-- FAISS retrieval <--- PDF/TXT ingestion
    +-- Configured hosted LLM
```

The FAISS document index, account/conversation database, and LangGraph
checkpointer are distinct stores. Conversation ownership is enforced by the
backend using the authenticated account, not by trusting a client-supplied
user ID. The conversation/thread ID is created by the backend and every
read/write is checked against its owner.

## Requirements and local setup

- Python 3.12 (the existing local virtual environment is Python 3.12).
- Node.js and npm.
- A configured supported LLM provider key/model and local embedding model.

Create a local `.env` from `.env.example`, then set the provider credentials,
model name, and a unique admin token. Never commit `.env`.

Install backend dependencies if creating a new environment:

```powershell
python -m pip install -r requirements.txt
```

Start FastAPI from the project root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
Set-Location .\frontend
npm install
npm run dev -- --host 127.0.0.1
```

Open the local URL printed by Vite. Its `/api` proxy forwards requests to
FastAPI at `127.0.0.1:8000`.

## Authentication and conversation data

Users can register and sign in from the chat screen. Passwords are hashed with
Argon2; API sessions are random bearer tokens whose hashes are stored server
side. The frontend keeps the current token in `sessionStorage` and calls the
logout endpoint to revoke it. Accounts, sessions, conversations, and messages
are stored in `MEDIBOT_AUTH_DB_PATH` (default
`data/medibot_auth.sqlite3`). LangGraph checkpoints remain in the separate
`MEDIBOT_MEMORY_DB_PATH` store.
Registration and login are limited to 10 attempts per client IP and action per
minute; the limiter stores a hash of the client address rather than the
address itself.

Current authentication endpoints:

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/register` | Create an account and issue a session |
| POST | `/auth/login` | Verify credentials and issue a session |
| GET | `/auth/me` | Return the authenticated account |
| POST | `/auth/logout` | Revoke the current session |
| POST/GET | `/chat/conversations/` | Create/list owned conversations |
| GET | `/chat/conversations/{id}/messages` | Read messages after ownership check |
| DELETE | `/chat/conversations/{id}` | Delete owned messages and graph checkpoint |
| POST | `/chat/` | Ask a question in an owned conversation |
| GET | `/health` | Basic service health |

SQLite is intended for local development at this stage. PostgreSQL support,
schema migrations, production session storage, and a production deployment
configuration have not yet been implemented.

## Admin access and network safety

Admin resource operations require `MEDIBOT_ADMIN_TOKEN`. They are additionally
restricted to IPv4/IPv6 loopback clients unless
`MEDIBOT_ADMIN_ALLOW_REMOTE=true` is explicitly configured. Keep the default
for local development and bind Uvicorn to `127.0.0.1`; do not expose the admin
routes publicly without a reviewed production access model, TLS, and suitable
network restrictions. The remote override bypasses only the loopback check;
the bearer token remains required.

Loopback restrictions do not protect against other software or users already
running on the same computer. Admin tokens are held in browser session
storage; use a unique token and avoid sharing admin sessions.

## Documents and evaluation

Admin accepts PDF and TXT documents up to 20 MiB, validates readable content,
and stages FAISS index rebuilds before replacing the active index. Uploaded
documents and the index are local application data. Only upload resources you
are authorized to use and review them for accuracy and suitability.

The current retrieval evaluation script is a small preliminary check, not a
medical benchmark. The requested comprehensive medical evaluation framework,
versioned 100+ case dataset, persisted evaluation dashboard, and qualified
clinical review remain future work.

## Testing

Run backend tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Run frontend checks:

```powershell
Set-Location .\frontend
npm run lint
npm run build
```

Pytest uses disposable checkpoint and account databases. Frontend component
tests are not configured yet.

## Known limitations and deployment status

- SQLite is not yet a production PostgreSQL setup, and migrations/backups are
  not implemented.
- Conversation history is available only within the current basic UI; search,
  renaming, date grouping, and profile/preferences are not implemented.
- Medical emergency recognition uses limited phrase matching. It is not a
  substitute for professional review or emergency services.
- The full retrieval/answer/faithfulness/citation/safety evaluation pipeline
  and dashboard are not implemented.
- No Render deployment configuration exists yet. The app is not deployed.

See [PROJECT_AUDIT.md](./PROJECT_AUDIT.md),
[IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md), and
[SECURITY_AUDIT.md](./SECURITY_AUDIT.md) for audited status and next steps.
