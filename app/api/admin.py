"""Admin API for uploading and automatically indexing Medibot resources."""  # Module docstring: describes that this file provides admin upload and auto-indexing endpoints.

import ipaddress  # Import ipaddress to check whether the client address is loopback.
import hmac
import json  # Import json to read and write the index status manifest.
import logging  # Import logging to record warnings and errors.
import os  # Import os to read environment variables.
import re  # Import re for filename sanitization.
import shutil  # Import shutil to remove temporary/backup directories.
import tempfile  # Import tempfile to create temporary files and directories.
import threading  # Import threading to create a lock for index rebuilds.
from pathlib import Path  # Import Path for filesystem path operations.
from typing import Annotated  # Import Annotated for FastAPI file parameter typing.
from urllib.parse import urlsplit

from dotenv import load_dotenv  # Import load_dotenv to load environment variables from .env.
from fastapi import (  # Begin importing FastAPI components.
    APIRouter,  # Import APIRouter to define admin routes.
    Depends,  # Import Depends to attach dependency checks to routes.
    File,  # Import File to declare uploaded file parameters.
    HTTPException,  # Import HTTPException to return HTTP errors.
    Request,  # Import Request to inspect the client connection.
    Response,
    UploadFile,  # Import UploadFile to handle uploaded files.
    status,  # Import status for HTTP status code constants.
)  # End FastAPI imports.
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pypdf.errors import PdfReadError  # Import PdfReadError to catch invalid PDF read errors.
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

# Resolve the project root and load configuration.  # Comment: explains the next two lines.
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # Resolve the project root from this file’s location.
load_dotenv(PROJECT_ROOT / ".env", override=False)  # Load .env without overriding existing environment variables.

from app.ingestion.chunking import split_documents  # Import the document chunking function.
from app.ingestion.document_loader import load_document, load_documents  # Import functions to load one or many documents.
from app.rag.vector_store import create_vector_store  # Import the function that creates the FAISS vector store.
from app.auth import client_identity, enforce_rate_limit
from app.db import get_db

logger = logging.getLogger(__name__)  # Create a module-level logger.
ADMIN_SESSION_COOKIE = "medibot_admin_session"
ADMIN_SESSION_MAX_AGE = 12 * 60 * 60
ADMIN_SESSION_SALT = "medibot-admin-session-v1"


class AdminLoginRequest(BaseModel):
    """Request body for the shared admin password."""

    password: str = Field(min_length=1, max_length=1024)


def _admin_session_serializer() -> URLSafeTimedSerializer:
    """Create the cookie signer only when a separate signing secret is set."""
    secret = os.getenv("MEDIBOT_ADMIN_SESSION_SECRET", "").strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin authentication is not configured.",
        )

    return URLSafeTimedSerializer(secret, salt=ADMIN_SESSION_SALT)


def _is_valid_admin_session(request: Request) -> bool:
    """Check the signature, contents, and 12-hour age of the session cookie."""
    cookie = request.cookies.get(ADMIN_SESSION_COOKIE)
    if not cookie:
        return False

    try:
        session = _admin_session_serializer().loads(
            cookie,
            max_age=ADMIN_SESSION_MAX_AGE,
        )
    except BadSignature:
        return False

    return session == {"admin": True}


def _is_loopback_client(request: Request) -> bool:
    """Return whether the direct ASGI client connection is from loopback."""
    client = request.client
    if client is None:
        return False

    try:
        return ipaddress.ip_address(client.host).is_loopback
    except (TypeError, ValueError):
        return False


def _is_local_admin_dev_mode(request: Request) -> bool:
    """Allow password-free admin access only in explicit local dev mode."""
    dev_mode = os.getenv("MEDIBOT_ADMIN_LOCAL_DEV", "").strip().lower()
    remote_enabled = os.getenv("MEDIBOT_ADMIN_ALLOW_REMOTE", "").strip().lower()
    return (
        _is_loopback_client(request)
        and dev_mode in {"1", "true", "yes"}
        and remote_enabled not in {"1", "true", "yes"}
    )


def require_admin_session(request: Request) -> None:
    """Require a session unless password-free local development is enabled."""
    if _is_local_admin_dev_mode(request):
        return

    if not os.getenv("MEDIBOT_ADMIN_PASSWORD", "").strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin authentication is not configured.",
        )

    if not _is_valid_admin_session(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin login is required.",
        )


def require_local_admin(request: Request) -> None:  # Define a dependency that restricts admin access to local clients.
    """Allow admin requests only when the ASGI peer address is loopback."""  # Docstring: explains the loopback-only policy.
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        host = request.headers.get("host", "")
        if origin and urlsplit(origin).netloc.casefold() != host.casefold():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cross-origin admin requests are not allowed.",
            )

    allow_remote = os.getenv("MEDIBOT_ADMIN_ALLOW_REMOTE", "").strip().lower()  # Read the remote-admin override flag and normalize it.
    if allow_remote in {"1", "true", "yes"} or _is_loopback_client(request):
        return

    if not _is_loopback_client(request):
        raise HTTPException(  # Raise an HTTP error for non-local clients.
            status_code=status.HTTP_403_FORBIDDEN,  # Return HTTP 403 Forbidden.
            detail="Admin resources are available only from this machine.",  # Explain that admin access is local-only.
        )  # End the HTTPException call.


router = APIRouter(  # Create the admin resources router.
    prefix="/admin/resources",  # Mount routes under /admin/resources.
    tags=["Admin Resources"],  # Tag routes for OpenAPI documentation.
    dependencies=[Depends(require_local_admin)],  # Apply the local-admin check to every route.
)  # End router creation.


@router.get("/auth/status")
def admin_auth_status(request: Request) -> dict[str, bool]:
    """Report whether this client can access admin resources and needs login."""
    local_dev_access = _is_local_admin_dev_mode(request)
    login_required = not local_dev_access
    configured = not login_required or bool(
        os.getenv("MEDIBOT_ADMIN_PASSWORD", "").strip()
        and os.getenv("MEDIBOT_ADMIN_SESSION_SECRET", "").strip()
    )
    authenticated = local_dev_access or (
        configured and _is_valid_admin_session(request)
    )
    return {
        "configured": configured,
        "authenticated": authenticated,
        "login_required": login_required,
    }


@router.post("/auth/login")
def admin_login(
    credentials: AdminLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    """Verify the configured password and issue an expiring HttpOnly cookie."""
    enforce_rate_limit(
        db,
        scope="admin:login",
        identity=client_identity(request),
        limit=5,
        window_seconds=15 * 60,
    )
    configured_password = os.getenv("MEDIBOT_ADMIN_PASSWORD", "")
    if not configured_password.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin authentication is not configured.",
        )

    serializer = _admin_session_serializer()
    if not hmac.compare_digest(
        credentials.password.encode("utf-8"),
        configured_password.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin password.",
        )

    secure_setting = os.getenv("MEDIBOT_ADMIN_COOKIE_SECURE", "").strip().lower()
    secure_cookie = (
        secure_setting in {"1", "true", "yes"}
        if secure_setting
        else request.url.scheme == "https"
    )
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE,
        value=serializer.dumps({"admin": True}),
        max_age=ADMIN_SESSION_MAX_AGE,
        httponly=True,
        secure=secure_cookie,
        samesite="strict",
        path="/",
    )
    return {"authenticated": True}


@router.post("/auth/logout")
def admin_logout(response: Response) -> dict[str, bool]:
    """Remove the admin session cookie from this browser."""
    response.delete_cookie(
        key=ADMIN_SESSION_COOKIE,
        path="/",
        httponly=True,
        samesite="strict",
    )
    return {"authenticated": False}


# Resolve paths from the project root so the API works from any directory.  # Comment: explains path resolution.
DATA_DIR = (  # Start computing the data directory path.
    PROJECT_ROOT / os.getenv("DATA_DIR", "data/raw")  # Join project root with DATA_DIR or default data/raw.
).resolve()  # Resolve the final data directory path.

_index_setting = Path(  # Start computing the configured vector store path.
    os.getenv("VECTORSTORE_DIR", "vectorstore/faiss_index")  # Read VECTORSTORE_DIR or use the default.
)  # End Path construction.
INDEX_DIR = (  # Start computing the absolute index directory.
    _index_setting  # Use the configured path directly if it is absolute.
    if _index_setting.is_absolute()  # Check whether the configured path is absolute.
    else PROJECT_ROOT / _index_setting  # Otherwise join it with the project root.
).resolve()  # Resolve the final index directory path.
# Stores indexing status so it survives page refreshes and restarts.  # Comment: explains the status manifest.
STATUS_FILE = INDEX_DIR.parent / "resource_index_status.json"  # Define the status manifest path beside the index directory.
INDEX_FAILURE_MESSAGE = (  # Start defining the user-facing indexing failure message.
    "The resource could not be indexed. "  # First part of the failure message.
    "Any existing knowledge index was preserved."  # Second part of the failure message.
)  # End the failure message definition.


def read_index_status() -> dict:  # Define a function to read the index status manifest.
    """Read the status manifest without exposing malformed manifest data."""  # Docstring: explains safe manifest reading.
    try:  # Start a try block for reading and parsing the manifest.
        manifest = json.loads(STATUS_FILE.read_text(encoding="utf-8"))  # Read the manifest file and parse it as JSON.
    except (FileNotFoundError, json.JSONDecodeError, OSError):  # Catch missing, malformed, or unreadable manifest files.
        return {}  # Return an empty manifest on failure.

    return manifest if isinstance(manifest, dict) else {}  # Return the manifest only if it is a dictionary.


def write_index_status(manifest: dict) -> None:  # Define a function to write the index status manifest.
    """Persist an index manifest using an atomic same-directory replace."""  # Docstring: explains atomic manifest writing.
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)  # Ensure the manifest directory exists.
    temp_status = None  # Initialize the temporary manifest path.

    try:  # Start a try block for writing the temporary manifest.
        with tempfile.NamedTemporaryFile(  # Create a temporary file in the same directory.
            mode="w",  # Open the temporary file in text write mode.
            encoding="utf-8",  # Use UTF-8 encoding.
            dir=STATUS_FILE.parent,  # Place the temporary file beside the final manifest.
            prefix=".resource-index-status-",  # Use a hidden temporary filename prefix.
            suffix=".tmp",  # Use a temporary filename suffix.
            delete=False,  # Keep the temporary file after closing it.
        ) as temp_file:  # Open the temporary file context.
            temp_status = Path(temp_file.name)  # Store the temporary file path.
            json.dump(manifest, temp_file, indent=2)  # Write the manifest as indented JSON.

        temp_status.replace(STATUS_FILE)  # Atomically replace the old manifest with the new one.
        temp_status = None  # Clear the temporary path after successful replacement.
    finally:  # Always run cleanup.
        if temp_status is not None:  # Check whether a temporary file still exists.
            temp_status.unlink(missing_ok=True)  # Delete the temporary file if present.


def save_index_status(chunks: list, documents: list) -> None:  # Define a function to save successful indexing status.
    """Persist successful indexing status and chunk counts."""  # Docstring: explains success status persistence.
    resources = {}  # Initialize per-resource chunk counts.

    # Count indexed chunks by their source filename.  # Comment: explains the next loop.
    for chunk in chunks:  # Iterate over all indexed chunks.
        source = chunk.metadata.get("source")  # Get the source filename from chunk metadata.
        if source:  # Check whether the chunk has a source.
            resources.setdefault(source, 0)  # Ensure the source has a chunk counter.
            resources[source] += 1  # Increment the chunk counter for the source.

    write_index_status(  # Write the successful index manifest.
        {  # Start the manifest dictionary.
            "index": {"status": "ready", "error": None},  # Mark the overall index as ready with no error.
            "resources": {  # Start per-resource status data.
                filename: {"status": "indexed", "chunks": count}  # Mark each resource as indexed with its chunk count.
                for filename, count in resources.items()  # Iterate over resource chunk counts.
            },  # End per-resource status data.
            "total_chunks": len(chunks),  # Record the total number of chunks.
            "documents_or_pages_loaded": len(documents),  # Record the number of loaded documents/pages.
        }  # End the manifest dictionary.
    )  # End write_index_status call.


def set_index_state(  # Define a function to update index state.
    state: str,  # Accept the new index state.
    *,  # Make following parameters keyword-only.
    filename: str | None = None,  # Accept an optional resource filename.
    error: str | None = None,  # Accept an optional safe error message.
) -> None:  # Return None.
    """Record a safe, user-facing indexing state."""  # Docstring: explains safe state recording.
    manifest = read_index_status()  # Read the current manifest.
    resources = manifest.get("resources")  # Get the resources section from the manifest.
    if not isinstance(resources, dict):  # Check whether resources is not a dictionary.
        resources = {}  # Create an empty resources dictionary.
        manifest["resources"] = resources  # Attach the empty resources dictionary to the manifest.

    if state == "building" and filename:  # Check whether a resource is being built.
        resources[filename] = {"status": "pending", "chunks": None}  # Mark the resource as pending.
    elif state == "failed" and filename:  # Check whether indexing failed for a resource.
        resources.pop(filename, None)  # Remove the failed resource from indexed resources.

    manifest["index"] = {  # Update the overall index status.
        "status": state,  # Store the new state.
        "error": error,  # Store the safe error message.
    }  # End the overall index status dictionary.
    write_index_status(manifest)  # Persist the updated manifest.


def index_details(manifest: dict) -> dict[str, str | bool | None]:  # Define a function to summarize index readiness.
    """Return a safe summary of current and last-known index readiness."""  # Docstring: explains the summary purpose.
    available = (  # Start checking whether the FAISS index files exist.
        (INDEX_DIR / "index.faiss").is_file()  # Check for the FAISS index file.
        and (INDEX_DIR / "index.pkl").is_file()  # Check for the FAISS metadata pickle file.
    )  # End availability check.
    index = manifest.get("index")  # Get the overall index status from the manifest.
    state = index.get("status") if isinstance(index, dict) else None  # Safely read the stored status.
    if not isinstance(state, str) or state not in {  # Check whether the stored state is invalid.
        "building",  # Allow the building state.
        "failed",  # Allow the failed state.
        "ready",  # Allow the ready state.
    }:  # End allowed-state check.
        state = "ready" if available else "not_ready"  # Derive state from file availability if stored state is invalid.
    elif state == "ready" and not available:  # Check whether stored state says ready but files are missing.
        state = "not_ready"  # Downgrade state to not_ready.

    messages = {  # Define user-facing status messages.
        "building": "The knowledge index is being rebuilt.",  # Message for building state.
        "failed": INDEX_FAILURE_MESSAGE,  # Message for failed state.
        "ready": "The knowledge index is ready.",  # Message for ready state.
        "not_ready": "No searchable knowledge index is available yet.",  # Message for not_ready state.
    }  # End messages dictionary.

    return {  # Return the safe index summary.
        "status": state,  # Include the resolved state.
        "available": available,  # Include whether index files exist.
        "message": messages[state],  # Include the matching user-facing message.
    }  # End return dictionary.
ALLOWED_EXTENSIONS = {".pdf", ".txt"}  # Define allowed upload file extensions.
MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20 MB  # Define the maximum upload size as 20 MB.

# Prevent two uploads from rebuilding/swapping the index simultaneously.  # Comment: explains the lock.
INDEX_LOCK = threading.Lock()  # Create a lock to serialize index rebuild operations.


def ensure_data_dir() -> None:  # Define a function to ensure the data directory exists.
    """Create the resource directory if it does not exist."""  # Docstring: explains directory creation.
    DATA_DIR.mkdir(parents=True, exist_ok=True)  # Create the data directory and parents if needed.


def resource_details(path: Path) -> dict:  # Define a function to return resource metadata.
    """Return safe metadata about a resource."""  # Docstring: explains metadata return.
    return {  # Return a dictionary of resource details.
        "name": path.name,  # Include the filename.
        "extension": path.suffix.lower(),  # Include the lowercase file extension.
        "size_bytes": path.stat().st_size,  # Include the file size in bytes.
    }  # End return dictionary.


def rebuild_index(uploaded_filename: str) -> dict:  # Define a function to rebuild the whole index.
    """  # Start function docstring.
    Rebuild the index using all available resources.  # Explain that all resources are reindexed.

    The new FAISS index is built in a separate directory. The existing  # Explain staged build.
    index is backed up before replacement and restored if replacement fails.  # Explain backup/restore behavior.
    """  # End function docstring.
    INDEX_DIR.parent.mkdir(parents=True, exist_ok=True)  # Ensure the index parent directory exists.

    # Temporary directories are placed beside the index to keep the  # Comment: explains why temporary dirs are beside the index.
    # replacement on the same drive/filesystem.  # Comment: continuation of the explanation.
    build_parent = Path(  # Start creating the temporary build parent directory.
        tempfile.mkdtemp(  # Create a temporary directory.
            prefix=".medibot-index-build-",  # Use a hidden build directory prefix.
            dir=INDEX_DIR.parent,  # Place it beside the index directory.
        )  # End mkdtemp call.
    )  # End Path construction.

    staged_index = build_parent / "faiss_index"  # Define the staged new index directory.
    backup_index = build_parent / "previous_index"  # Define the backup directory for the old index.

    old_index_moved = False  # Track whether the old index was moved to backup.
    new_index_installed = False  # Track whether the new index was installed.

    try:  # Start the main rebuild try block.
        documents = load_documents(DATA_DIR)  # Load all documents from the data directory.
        chunks = split_documents(  # Split loaded documents into chunks.
            documents,  # Pass the loaded documents.
            chunk_size=800,  # Use a chunk size of 800 characters/tokens as configured.
            chunk_overlap=120,  # Use 120 overlap between chunks.
        )  # End split_documents call.
        uploaded_chunks = [  # Start collecting chunks from the uploaded file.
            chunk  # Keep each chunk.
            for chunk in chunks  # Iterate over all chunks.
            if chunk.metadata.get("source") == uploaded_filename  # Keep only chunks from the uploaded filename.
        ]  # End uploaded_chunks list.

        if not uploaded_chunks:  # Check whether the upload produced no chunks.
            raise ValueError(  # Raise a value error for unreadable/empty upload.
                "No searchable text chunks were extracted from the upload."  # Explain why indexing failed.
            )  # End ValueError call.

        create_vector_store(chunks, staged_index)  # Build the new FAISS vector store in the staged directory.

        if not (staged_index / "index.faiss").is_file():  # Check whether the staged FAISS index file exists.
            raise RuntimeError("The staged FAISS index is incomplete.")  # Fail if the FAISS index file is missing.

        if not (staged_index / "index.pkl").is_file():  # Check whether the staged FAISS metadata file exists.
            raise RuntimeError("The staged FAISS metadata is incomplete.")  # Fail if the metadata file is missing.

        if INDEX_DIR.exists():  # Check whether an old index directory exists.
            INDEX_DIR.replace(backup_index)  # Move the old index to the backup location.
            old_index_moved = True  # Record that the old index was moved.

        staged_index.replace(INDEX_DIR)  # Move the staged index into the live index location.
        new_index_installed = True  # Record that the new index was installed.

        # Keep the previous index available until status persistence succeeds.  # Comment: explains backup retention.
        save_index_status(chunks, documents)  # Persist successful indexing status.

        if backup_index.exists():  # Check whether the backup index still exists.
            try:  # Start a try block for deleting the backup.
                shutil.rmtree(backup_index)  # Remove the backup index directory.
                old_index_moved = False  # Record that the old index is no longer moved.
            except OSError:  # Catch backup deletion errors.
                logger.warning("Could not remove the temporary previous index.")  # Log a warning but continue.

        logger.info("Resource indexing completed successfully.")  # Log successful indexing.
        return {  # Return the indexing result.
            "status": "indexed",  # Report successful indexing.
            "filename": uploaded_filename,  # Include the uploaded filename.
            "chunks_created": len(uploaded_chunks),  # Include chunks created from the upload.
            "total_chunks_in_index": len(chunks),  # Include total chunks in the index.
            "documents_or_pages_loaded": len(documents),  # Include loaded document/page count.
        }  # End return dictionary.

    except Exception:  # Catch any exception during rebuild.
        if new_index_installed and INDEX_DIR.exists():  # Check whether the new index was installed.
            INDEX_DIR.replace(staged_index)  # Move the new index back to staging.
            new_index_installed = False  # Record that the new index is no longer installed.

        if old_index_moved and backup_index.exists():  # Check whether the old index is in backup.
            backup_index.replace(INDEX_DIR)  # Restore the old index to the live location.
            old_index_moved = False  # Record that the old index is restored.

        raise  # Re-raise the original exception after rollback.

    finally:  # Always run cleanup.
        try:  # Start a try block for removing the build parent.
            shutil.rmtree(build_parent)  # Remove the temporary build directory.
        except FileNotFoundError:  # Catch the case where the build directory is already gone.
            pass  # Ignore missing build directory.
        except OSError:  # Catch other removal errors.
            logger.warning("Could not remove the temporary index build directory.")  # Log a warning.

@router.get("/", dependencies=[Depends(require_admin_session)])
def list_resources() -> dict:  # Define the endpoint to list resources.
    """List resources with their persistent indexing status."""  # Docstring: explains the listing purpose.
    ensure_data_dir()  # Ensure the data directory exists.
    manifest = read_index_status()  # Read the persistent index status manifest.
    indexed_resources = manifest.get("resources")  # Get per-resource indexing status.
    if not isinstance(indexed_resources, dict):  # Check whether per-resource status is invalid.
        indexed_resources = {}  # Use an empty dictionary if invalid.

    resources = []  # Initialize the resource list.

    for path in sorted(DATA_DIR.iterdir()):  # Iterate over sorted entries in the data directory.
        if (  # Start filtering invalid entries.
            path.is_symlink()  # Skip symbolic links.
            or not path.is_file()  # Skip non-files.
            or path.suffix.lower() not in ALLOWED_EXTENSIONS  # Skip files with disallowed extensions.
        ):  # End filter condition.
            continue  # Skip this entry.

        details = resource_details(path)  # Get safe metadata for the resource.
        indexing = indexed_resources.get(path.name)  # Get indexing status for this resource.
        if not isinstance(indexing, dict):  # Check whether indexing status is invalid.
            indexing = {}  # Use an empty dictionary if invalid.

        resource_status = indexing.get("status")  # Read the resource indexing status.
        if not isinstance(resource_status, str) or resource_status not in {  # Check whether status is invalid.
            "indexed",  # Allow indexed status.
            "pending",  # Allow pending status.
            "failed",  # Allow failed status.
        }:  # End status validity check.
            resource_status = "not_indexed"  # Default to not_indexed.

        chunks = indexing.get("chunks")  # Read the chunk count.
        if not isinstance(chunks, int) or chunks < 0:  # Check whether chunk count is invalid.
            chunks = None  # Use None for invalid chunk counts.

        details["index_status"] = resource_status  # Add indexing status to resource details.
        details["chunks"] = chunks  # Add chunk count to resource details.

        resources.append(details)  # Add the resource details to the list.

    return {  # Return the listing response.
        "count": len(resources),  # Include the number of resources.
        "resources": resources,  # Include the resource details.
        "index": index_details(manifest),  # Include the overall index summary.
    }  # End return dictionary.

@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_session)],
)
def upload_resource(  # Define the upload endpoint.
    file: Annotated[UploadFile, File(...)],  # Accept a required uploaded file.
) -> dict:  # Return a dictionary response.
    """Save a resource, index it automatically, and report the result."""  # Docstring: explains upload and indexing.
    original_name = file.filename or ""  # Get the original filename or an empty string.

    if (  # Start validating the original filename.
        not original_name  # Reject missing filename.
        or len(original_name) > 255  # Reject filenames longer than 255 characters.
        or "/" in original_name  # Reject forward slash path components.
        or "\\" in original_name  # Reject backslash path components.
        or any(  # Start checking for control characters.
            ord(character) < 32 or ord(character) == 127  # Detect ASCII control characters.
            for character in original_name  # Iterate over filename characters.
        )  # End control-character check.
    ):  # End filename validation condition.
        raise HTTPException(  # Raise an HTTP error for invalid filenames.
            status_code=400,  # Return HTTP 400 Bad Request.
            detail="A valid filename without path components is required.",  # Explain the filename requirement.
        )  # End HTTPException call.

    suffix = Path(original_name).suffix.lower()  # Get the lowercase file extension.

    if suffix not in ALLOWED_EXTENSIONS:  # Check whether the extension is allowed.
        raise HTTPException(  # Raise an HTTP error for disallowed file types.
            status_code=415,  # Return HTTP 415 Unsupported Media Type.
            detail="Upload only PDF or TXT files.",  # Explain allowed file types.
        )  # End HTTPException call.

    # Sanitize the filename to prevent path traversal.  # Comment: explains filename sanitization.
    safe_stem = re.sub(  # Start sanitizing the filename stem.
        r"[^A-Za-z0-9._-]+",  # Replace disallowed characters with underscores.
        "_",  # Use underscore as the replacement.
        Path(original_name).stem,  # Use the original filename without extension.
    ).strip("._-")[:100]  # Strip leading/trailing punctuation and limit length.

    if not safe_stem:  # Check whether sanitization produced an empty stem.
        raise HTTPException(  # Raise an HTTP error for an invalid sanitized filename.
            status_code=400,  # Return HTTP 400 Bad Request.
            detail="Invalid filename.",  # Explain that the filename is invalid.
        )  # End HTTPException call.

    destination = DATA_DIR / f"{safe_stem}{suffix}"  # Build the final destination path.

    temp_path = None  # Initialize the temporary upload path.
    total_bytes = 0  # Initialize the uploaded byte counter.
    uploaded_and_saved = False  # Track whether the file was saved to its final destination.

    try:  # Start the main upload try block.
        with INDEX_LOCK:  # Acquire the index lock to prevent concurrent rebuilds.
            ensure_data_dir()  # Ensure the data directory exists.

            if destination.exists():  # Check whether a resource with this name already exists.
                raise HTTPException(  # Raise an HTTP error for duplicate resources.
                    status_code=409,  # Return HTTP 409 Conflict.
                    detail="A resource with this filename already exists.",  # Explain the duplicate filename.
                )  # End HTTPException call.

            with tempfile.NamedTemporaryFile(  # Create a temporary upload file.
                mode="wb",  # Open the temporary file in binary write mode.
                dir=DATA_DIR,  # Place it in the data directory.
                prefix=".upload_",  # Use a hidden upload filename prefix.
                suffix=suffix,  # Preserve the file extension.
                delete=False,  # Keep the temporary file after closing.
            ) as temp_file:  # Open the temporary file context.
                temp_path = Path(temp_file.name)  # Store the temporary file path.

                while True:  # Start reading the upload in blocks.
                    block = file.file.read(1024 * 1024)  # Read up to 1 MB from the upload.
                    if not block:  # Check whether the upload is finished.
                        break  # Stop reading when no more data is available.

                    total_bytes += len(block)  # Add the block size to the total byte count.
                    if total_bytes > MAX_UPLOAD_SIZE:  # Check whether the upload exceeds the size limit.
                        raise HTTPException(  # Raise an HTTP error for oversized uploads.
                            status_code=413,  # Return HTTP 413 Payload Too Large.
                            detail="File exceeds the 20 MB upload limit.",  # Explain the size limit.
                        )  # End HTTPException call.

                    temp_file.write(block)  # Write the block to the temporary file.

            if total_bytes == 0:  # Check whether the uploaded file is empty.
                raise HTTPException(  # Raise an HTTP error for empty uploads.
                    status_code=400,  # Return HTTP 400 Bad Request.
                    detail="The uploaded file is empty.",  # Explain that the file is empty.
                )  # End HTTPException call.

            if suffix == ".pdf":  # Check whether the uploaded file is a PDF.
                with temp_path.open("rb") as staged_file:  # Open the staged PDF for inspection.
                    if b"%PDF-" not in staged_file.read(1024):  # Check the PDF signature in the first 1 KB.
                        raise HTTPException(  # Raise an HTTP error for invalid PDFs.
                            status_code=422,  # Return HTTP 422 Unprocessable Entity.
                            detail="The uploaded PDF is not valid.",  # Explain that the PDF is invalid.
                        )  # End HTTPException call.

            try:  # Start a try block for document validation.
                validated_documents = load_document(temp_path)  # Load the uploaded document to validate it.
            except (OSError, UnicodeError, ValueError, PdfReadError) as exc:  # Catch document read/parse errors.
                raise HTTPException(  # Raise an HTTP error for unreadable documents.
                    status_code=422,  # Return HTTP 422 Unprocessable Entity.
                    detail="The uploaded document could not be read.",  # Explain the read failure.
                ) from exc  # Chain the original exception.

            if not validated_documents:  # Check whether the document produced no readable content.
                raise HTTPException(  # Raise an HTTP error for documents without readable text.
                    status_code=422,  # Return HTTP 422 Unprocessable Entity.
                    detail="The uploaded document contains no readable text.",  # Explain the content problem.
                )  # End HTTPException call.

            if destination.exists():  # Recheck for a duplicate before moving the file.
                raise HTTPException(  # Raise an HTTP error for duplicate resources.
                    status_code=409,  # Return HTTP 409 Conflict.
                    detail="A resource with this filename already exists.",  # Explain the duplicate filename.
                )  # End HTTPException call.

            temp_path.replace(destination)  # Atomically move the temporary file to its final destination.
            temp_path = None  # Clear the temporary path after successful move.
            uploaded_and_saved = True  # Record that the upload was saved.

            set_index_state("building", filename=destination.name)  # Mark the new resource as pending indexing.
            result = rebuild_index(destination.name)  # Rebuild the index including the new resource.

        return {  # Return the successful upload response.
            "message": "Resource uploaded and indexed successfully.",  # Report success.
            "resource": resource_details(destination),  # Include saved resource metadata.
            "indexing": result,  # Include indexing results.
        }  # End return dictionary.

    except HTTPException:  # Catch HTTP errors raised intentionally.
        raise  # Re-raise the HTTP error unchanged.

    except Exception as exc:  # Catch unexpected upload/indexing errors.
        if uploaded_and_saved:  # Check whether the file was already saved.
            try:  # Start a try block for cleanup.
                destination.unlink(missing_ok=True)  # Remove the failed saved resource.
            except OSError:  # Catch cleanup errors.
                logger.exception("Could not remove the failed resource upload.")  # Log cleanup failure.

        try:  # Start a try block for recording failure state.
            set_index_state(  # Update the manifest to failed state.
                "failed",  # Set the index state to failed.
                filename=destination.name,  # Record the failed resource filename.
                error=INDEX_FAILURE_MESSAGE,  # Store the safe failure message.
            )  # End set_index_state call.
        except OSError:  # Catch manifest write errors.
            logger.exception("Could not persist failed indexing status.")  # Log manifest failure.

        logger.exception("Resource upload or indexing failed.")  # Log the full upload/indexing exception.

        raise HTTPException(  # Raise a generic HTTP error to the client.
            status_code=500,  # Return HTTP 500 Internal Server Error.
            detail=INDEX_FAILURE_MESSAGE,  # Return the safe failure message.
        ) from exc  # Chain the original exception.

    finally:  # Always run final cleanup.
        if temp_path is not None:  # Check whether a temporary upload file remains.
            temp_path.unlink(missing_ok=True)  # Delete the temporary upload file if present.

        file.file.close()  # Close the uploaded file stream.