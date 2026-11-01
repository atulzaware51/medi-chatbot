# Medibot admin resources completion

## Features implemented

- Added loopback-only protection to both admin resource endpoints using the
  ASGI peer address. Missing and malformed addresses fail closed; forwarded,
  origin, and host headers are not used to establish local access.
- Added safe resource listing with file metadata and global index readiness.
- Validated filenames, extensions, empty and unreadable content, duplicate
  uploads, and the 20 MiB upload cap. Uploads use temporary files and are
  published only after validation.
- Built replacement FAISS indexes in a staging directory. The active index is
  retained until the new index and its status manifest are ready; failures
  roll back the swap and return a generic client-safe error.
- Added readable index state, upload feedback, refresh/retry, and responsive
  resource-list states in the React admin screen. The UI continues to use the
  existing `/api` proxy and does not change the chat or retrieval pipeline.
- Made checkpoint storage configurable with `MEDIBOT_MEMORY_DB_PATH`.
  Pytest now redirects the shared checkpointer to a disposable database and
  removes it at session end. Admin test resources and indexes use disposable
  directories.
- Documented local-only startup and security limitations. Added ignore rules
  for SQLite WAL/SHM sidecars.

## Files changed

- `.gitignore`
- `README.md`
- `app/api/admin.py`
- `app/memory/checkpointer.py`
- `frontend/src/admin/AdminResources.jsx`
- `frontend/src/App.css`
- `tests/conftest.py`
- `tests/test_admin_security.py`
- `tests/test_memory_isolation.py`
- `reports/medibot_admin_resources_completion.md` (this report)

No dependency manifests or lockfiles were changed.

## Security decisions and limitations

- Admin requests are restricted to IPv4/IPv6 loopback peers. This reduces
  exposure to other machines on the network; it is not user authentication and
  does not protect against other software or users on the same computer.
- Uvicorn and Vite startup instructions bind to `127.0.0.1`.
- Resource errors and index-state messages returned to clients are generic;
  internal exceptions, document text, credentials, and filesystem paths are
  not included.
- Indexing remains synchronous. The UI shows an indeterminate loading
  indicator rather than a byte-level progress percentage.
- Scanned PDFs without extractable text are not OCR-processed and are rejected
  if they produce no searchable content.
- The backend suite reports one existing `langchain-community` deprecation
  warning; no tests fail.

## Commands run and results

All Python commands used the existing `.venv`; no packages were installed.

| Command | Result |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest -q` (baseline, before edits) | 36 passed, 1 warning |
| `.\.venv\Scripts\python.exe -m compileall -q app tests` (baseline and final) | Passed |
| `.\.venv\Scripts\python.exe -m pip check` (baseline and final) | No broken requirements |
| `npm run lint` from `frontend` (baseline) | Failed on the existing `react-hooks/set-state-in-effect` diagnostic in `AdminResources.jsx`; resolved without suppressing the rule |
| `npm run build` from `frontend` (baseline and final) | Passed |
| `.\.venv\Scripts\python.exe -m pytest -q tests\test_admin_security.py tests\test_memory_isolation.py tests\test_chat_api.py` (final) | 26 passed, 1 warning |
| `.\.venv\Scripts\python.exe -m pytest -q` (final) | 59 passed, 1 warning |
| `npm run lint` from `frontend` (final) | Passed |

During implementation, early focused runs exposed test-harness assumptions
that were corrected; the final focused and full runs above pass. The frontend
package has no test script, so lint and production build were its available
automated checks.

## Data preservation note

The initial baseline pytest run occurred before the checkpoint-isolation
fixture was added. The existing memory workflow tests therefore ran against
the application's default SQLite checkpoint database and may have appended
their generated test conversations. No checkpoint contents were inspected,
copied, deleted, or reset. After isolation was added, focused and full test
runs used a temporary checkpoint database that was removed at session end.
The existing database's size and modification time did not change during
those final runs. SQLite WAL/SHM sidecars were left untouched because they may
belong to an active SQLite connection; the new ignore rules do not delete
them.

The starting Git status showed the project files as untracked. Final review
compared the changed existing source files with the timestamped external
backup at
`%LOCALAPPDATA%\Medibot\backups\admin-resources-20261030-143422`.
The workspace passed a write probe. No credentials or private document
contents were added.

## Start the application

From the project root, start the backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
Set-Location .\frontend
npm run dev -- --host 127.0.0.1
```

Open the local address printed by Vite.

## Manual verification steps

1. Start both processes using the commands above and open the Vite local URL.
2. Select **Admin Resources**. Confirm that resources and index readiness load;
   use **Refresh list** to retry after an API error.
3. Upload a non-empty PDF with extractable text or a TXT file smaller than
   20 MiB. Confirm the processing indicator remains visible during synchronous
   indexing, then verify the success message, resource row, chunk count, and
   **Ready** index state.
4. Retry the same filename and try an unsupported, empty, malformed, invalid,
   or oversized upload. Confirm a readable error is displayed and no rejected
   file appears in the resource list.
5. In chat, ask a question covered by the uploaded material. Confirm the
   existing answer/source behavior still works. The automated tests mock
   expensive indexing; a normal successful manual upload requires the local
   embedding model and the application's configured chat provider.

## Remaining limitations

- Loopback checks are not a substitute for authentication on a shared machine.
- Indexing blocks the upload request until it finishes.
- OCR and automated PDF repair are not provided.
- The baseline-test checkpoint caveat above cannot be reversed safely without
  risking existing conversation data.
