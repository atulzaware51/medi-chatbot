# Medibot Project Audit

Audit date: 2026-10-31

## Scope and baseline

The audit inspected the existing FastAPI/LangGraph/RAG backend, React/Vite
frontend, current tests, dependency manifests, ignore rules, and available
deployment configuration. `.env` and private document/database contents were
not inspected.

The worktree has no commits yet and the application files are untracked. This
means Git cannot distinguish the initial project from later edits; preserve
existing files and review the complete worktree before the first commit.

| Check | Baseline result |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest -q` | 58 passed, 1 LangChain deprecation warning |
| `npm run build` in `frontend` | Passed |
| `npm run lint` in `frontend` | 0 errors, 1 React Hook dependency warning |
| Frontend component tests | No test script or component-test setup found |
| Render configuration | No `render.yaml` present |
| Root Dockerfile | No `Dockerfile` present |

## Existing architecture

- React 19 and Vite provide a single chat/admin frontend. Vite proxies `/api`
  requests to FastAPI during development.
- FastAPI exposes the chat API, admin resource API, and health endpoint. It
  serves `frontend/dist` when that directory exists.
- LangGraph runs a single answer node and saves message state with a shared
  SQLite checkpointer. The frontend creates a random thread ID in memory; it
  does not restore a selected conversation or keep a history list.
- Ingestion accepts PDF/TXT resources, chunks the extracted text, embeds it
  with Sentence Transformers, and stores the FAISS index on disk. Index
  replacement is staged and has rollback handling.
- Retrieval uses a configurable top-k and distance threshold. The answer
  service provides citations, a no-evidence response in common cases, and
  phrase-based emergency handling.
- Tests cover chat validation, memory thread separation, document loading,
  chunking, retrieval, answer grounding/safety examples, and admin upload and
  indexing behavior.

## Findings and gaps to address

1. **Authentication and user-owned history are not implemented.** The chat
   endpoint accepts caller-provided thread IDs and there are no user accounts,
   conversations/messages tables, or ownership checks. The frontend does not
   provide login, registration, profile, or persistent history management.
2. **The requested production persistence is absent.** SQLite checkpoints are
   the only application persistence. There is no PostgreSQL configuration or
   migration system.
3. **Medical safety is limited and rule-based.** Current deterministic
   emergency handling covers a small set of phrases. Tests do not yet cover
   the full requested set, and this software has not been medically validated.
4. **Evaluation is preliminary.** `scripts/evaluate_retrieval.py` has a small
   hand-authored source-level set; it does not calculate the requested
   retrieval, answer, faithfulness, citation, or safety metrics, nor persist
   runs.
5. **The UI is a working starter interface, not the requested full product.**
   It has chat and admin-resource screens, but no account/profile/history or
   evaluation dashboard. Browser Back/Forward state synchronization and
   frontend automated tests remain to be implemented.
6. **Deployment and dependency reproducibility are incomplete.** Dependencies
   in `requirements.txt` are unpinned and include Streamlit/Requests although
   the current frontend is React. Render configuration, database migrations,
   and production API/CORS configuration are absent.
7. **Lint has a warning.** `frontend/src/admin/AdminResources.jsx` has a
   `useCallback` dependency warning for `token` and `onUnauthorized`.
8. **Documentation is incomplete for the requested portfolio/deployment
   scope.** The existing README documents local startup and a limited set of
   local-data constraints, but not the complete deployment, authentication,
   evaluation, or safety design.

## Preservation and safety notes

- `.gitignore` excludes `.env`, Python environments, local databases, raw
  documents, and FAISS indexes. Keep these exclusions and verify no private
  data is staged before the initial commit.
- The application should continue to be described as educational information,
  not a diagnostic or clinically validated system.
- No dependencies were installed and no existing data or credentials were
  read or changed during this audit.

See [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) for the proposed
incremental work and [SECURITY_AUDIT.md](./SECURITY_AUDIT.md) for the
security findings.

## Follow-up implementation status

After the baseline, the two security findings were addressed locally:
registration/login now use Argon2 and expiring opaque sessions; chat
conversations and messages are persisted with authenticated ownership checks;
and admin routes reject non-loopback peers unless an explicit remote-access
override is configured. The frontend now supports account sign-in, basic
conversation restoration/deletion, and browser Back/Forward navigation.

These updates do not complete the original production scope. PostgreSQL,
migrations, comprehensive safety/evaluation features, a full profile/history
experience, Render configuration, and deployment verification remain open.
