"""Admin resource API validation, isolation, and loopback security tests."""

import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document

from app.api import admin
from app.main import app


@pytest.fixture
def resource_paths(monkeypatch):
    with tempfile.TemporaryDirectory(prefix="medibot-admin-test-") as directory:
        temp_path = Path(directory)
        data_dir = temp_path / "resources"
        index_dir = temp_path / "index"
        status_file = temp_path / "index-status.json"
        monkeypatch.setattr(admin, "DATA_DIR", data_dir)
        monkeypatch.setattr(admin, "INDEX_DIR", index_dir)
        monkeypatch.setattr(admin, "STATUS_FILE", status_file)
        yield data_dir, index_dir, status_file


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("MEDIBOT_ADMIN_ALLOW_REMOTE", raising=False)
    monkeypatch.setenv("MEDIBOT_ADMIN_LOCAL_DEV", "true")
    monkeypatch.setenv("MEDIBOT_ADMIN_PASSWORD", "test-admin-password")
    monkeypatch.setenv(
        "MEDIBOT_ADMIN_SESSION_SECRET",
        "test-only-session-signing-secret-with-enough-entropy",
    )

    test_client = TestClient(
        app,
        client=("127.0.0.1", 43120),
    )
    return test_client


def install_successful_rebuild(monkeypatch, resource_paths):
    data_dir, index_dir, _ = resource_paths

    def fake_rebuild(filename):
        index_dir.mkdir(parents=True, exist_ok=True)
        (index_dir / "index.faiss").write_bytes(b"test index")
        (index_dir / "index.pkl").write_bytes(b"test metadata")
        chunk = Document(
            page_content="indexed test content",
            metadata={"source": filename},
        )
        admin.save_index_status([chunk], [chunk])
        return {
            "status": "indexed",
            "filename": filename,
            "chunks_created": 1,
            "total_chunks_in_index": 1,
            "documents_or_pages_loaded": 1,
        }

    monkeypatch.setattr(admin, "rebuild_index", fake_rebuild)
    return data_dir


def test_list_resources_returns_safe_metadata(client, resource_paths):
    data_dir, index_dir, status_file = resource_paths
    data_dir.mkdir()
    (data_dir / "guide.txt").write_text("Local resource", encoding="utf-8")
    index_dir.mkdir()
    (index_dir / "index.faiss").write_bytes(b"index")
    (index_dir / "index.pkl").write_bytes(b"metadata")
    admin.save_index_status(
        [Document(page_content="text", metadata={"source": "guide.txt"})],
        [Document(page_content="text", metadata={"source": "guide.txt"})],
    )

    response = client.get("/admin/resources/")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["resources"] == [
        {
            "name": "guide.txt",
            "extension": ".txt",
            "size_bytes": len(b"Local resource"),
            "index_status": "indexed",
            "chunks": 1,
        }
    ]
    assert body["index"]["status"] == "ready"
    assert body["index"]["available"] is True
    assert str(data_dir) not in response.text
    assert str(index_dir) not in response.text
    assert status_file.exists()


def test_list_resources_does_not_return_untrusted_status_manifest_values(
    client,
    resource_paths,
):
    data_dir, _, status_file = resource_paths
    data_dir.mkdir()
    (data_dir / "guide.txt").write_text("Local resource", encoding="utf-8")
    status_file.write_text(
        json.dumps(
            {
                "index": {
                    "status": "failed",
                    "error": "C:/private/internal-detail",
                },
                "resources": {
                    "guide.txt": {
                        "status": {"private": "internal-detail"},
                        "chunks": "internal-detail",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    response = client.get("/admin/resources/")

    assert response.status_code == 200
    body = response.json()
    assert body["index"]["message"] == admin.INDEX_FAILURE_MESSAGE
    assert body["resources"][0]["index_status"] == "not_indexed"
    assert body["resources"][0]["chunks"] is None
    assert "private" not in response.text
    assert "internal-detail" not in response.text


def test_valid_txt_upload_is_indexed(client, resource_paths, monkeypatch):
    data_dir = install_successful_rebuild(monkeypatch, resource_paths)

    response = client.post(
        "/admin/resources/upload",
        files={
            "file": (
                "guide.txt",
                b"Useful medical information.",
                "text/plain",
            )
        },
    )

    assert response.status_code == 201
    assert response.json()["resource"]["name"] == "guide.txt"
    assert response.json()["indexing"]["status"] == "indexed"
    assert (data_dir / "guide.txt").read_bytes() == b"Useful medical information."
    assert list(data_dir.iterdir()) == [data_dir / "guide.txt"]


def test_valid_pdf_upload_is_indexed(client, resource_paths, monkeypatch):
    data_dir = install_successful_rebuild(monkeypatch, resource_paths)
    monkeypatch.setattr(
        admin,
        "load_document",
        lambda path: [
            Document(page_content="Extracted PDF text", metadata={})
        ],
    )

    response = client.post(
        "/admin/resources/upload",
        files={
            "file": (
                "guide.pdf",
                b"%PDF-1.7\nfake but validated",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 201
    assert response.json()["resource"]["extension"] == ".pdf"
    assert (data_dir / "guide.pdf").is_file()


@pytest.mark.parametrize(
    ("filename", "content", "expected_status"),
    [
        ("empty.txt", b"", 400),
        ("blank.txt", b" \n\t", 422),
        ("unsupported.csv", b"content", 415),
        ("bad.pdf", b"not a PDF", 422),
    ],
)
def test_upload_rejects_empty_unsupported_and_invalid_content(
    client,
    resource_paths,
    filename,
    content,
    expected_status,
):
    response = client.post(
        "/admin/resources/upload",
        files={"file": (filename, content, "application/octet-stream")},
    )

    assert response.status_code == expected_status
    data_dir = resource_paths[0]
    if data_dir.exists():
        assert not list(data_dir.glob(".upload_*"))


def test_upload_rejects_oversized_file(client, resource_paths, monkeypatch):
    assert admin.MAX_UPLOAD_SIZE == 20 * 1024 * 1024
    monkeypatch.setattr(admin, "MAX_UPLOAD_SIZE", 64)
    payload = b"x" * 65

    response = client.post(
        "/admin/resources/upload",
        files={"file": ("large.txt", payload, "text/plain")},
    )

    assert response.status_code == 413
    data_dir = resource_paths[0]
    if data_dir.exists():
        assert not list(data_dir.glob(".upload_*"))


def test_duplicate_upload_is_rejected(client, resource_paths, monkeypatch):
    data_dir = install_successful_rebuild(monkeypatch, resource_paths)
    first = client.post(
        "/admin/resources/upload",
        files={"file": ("guide.txt", b"Valid text", "text/plain")},
    )
    second = client.post(
        "/admin/resources/upload",
        files={"file": ("guide.txt", b"Different text", "text/plain")},
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert (data_dir / "guide.txt").read_bytes() == b"Valid text"


@pytest.mark.parametrize(
    "filename",
    ["../outside.txt", r"..\outside.txt", "folder/name.txt", "!!!.txt"],
)
def test_malformed_and_traversal_filenames_are_rejected(
    client,
    resource_paths,
    filename,
):
    response = client.post(
        "/admin/resources/upload",
        files={"file": (filename, b"Valid text", "text/plain")},
    )

    assert response.status_code == 400
    assert not resource_paths[0].exists()


def test_failed_indexing_keeps_the_previous_index(
    client,
    resource_paths,
    monkeypatch,
):
    data_dir, index_dir, status_file = resource_paths
    data_dir.mkdir()
    index_dir.mkdir()
    original_faiss = b"previous active index"
    original_metadata = b"previous metadata"
    (index_dir / "index.faiss").write_bytes(original_faiss)
    (index_dir / "index.pkl").write_bytes(original_metadata)
    (data_dir / "existing.txt").write_text("Existing text", encoding="utf-8")
    monkeypatch.setattr(
        admin,
        "load_documents",
        lambda path: [
            Document(
                page_content="new resource text",
                metadata={"source": "new.txt"},
            )
        ],
    )
    monkeypatch.setattr(
        admin,
        "split_documents",
        lambda documents, **kwargs: documents,
    )

    def fail_index_creation(chunks, path):
        raise RuntimeError("private filesystem detail")

    monkeypatch.setattr(
        admin,
        "create_vector_store",
        fail_index_creation,
    )

    response = client.post(
        "/admin/resources/upload",
        files={"file": ("new.txt", b"New resource text", "text/plain")},
    )

    assert response.status_code == 500
    assert "private filesystem detail" not in response.text
    assert response.json()["detail"] == admin.INDEX_FAILURE_MESSAGE
    assert (index_dir / "index.faiss").read_bytes() == original_faiss
    assert (index_dir / "index.pkl").read_bytes() == original_metadata
    assert not (data_dir / "new.txt").exists()
    assert (
        json.loads(status_file.read_text(encoding="utf-8"))["index"]["status"]
        == "failed"
    )
    assert not list(index_dir.parent.glob(".medibot-index-build-*"))


def test_status_persistence_failure_rolls_back_index_swap(
    client,
    resource_paths,
    monkeypatch,
):
    data_dir, index_dir, _ = resource_paths
    data_dir.mkdir()
    index_dir.mkdir()
    original_faiss = b"previous active index"
    original_metadata = b"previous metadata"
    (index_dir / "index.faiss").write_bytes(original_faiss)
    (index_dir / "index.pkl").write_bytes(original_metadata)
    chunk = Document(
        page_content="new resource text",
        metadata={"source": "new.txt"},
    )
    monkeypatch.setattr(admin, "load_documents", lambda path: [chunk])
    monkeypatch.setattr(
        admin,
        "split_documents",
        lambda documents, **kwargs: documents,
    )

    def create_staged_index(chunks, path):
        path.mkdir()
        (path / "index.faiss").write_bytes(b"new index")
        (path / "index.pkl").write_bytes(b"new metadata")

    def fail_status_persistence(chunks, documents):
        raise OSError("private status path")

    monkeypatch.setattr(admin, "create_vector_store", create_staged_index)
    monkeypatch.setattr(admin, "save_index_status", fail_status_persistence)

    response = client.post(
        "/admin/resources/upload",
        files={"file": ("new.txt", b"New resource text", "text/plain")},
    )

    assert response.status_code == 500
    assert "private status path" not in response.text
    assert (index_dir / "index.faiss").read_bytes() == original_faiss
    assert (index_dir / "index.pkl").read_bytes() == original_metadata
    assert not (data_dir / "new.txt").exists()
    assert not list(index_dir.parent.glob(".medibot-index-build-*"))




def test_admin_is_directly_available_to_loopback_clients(monkeypatch):
    monkeypatch.setenv("MEDIBOT_ADMIN_ALLOW_REMOTE", "false")
    monkeypatch.setenv("MEDIBOT_ADMIN_LOCAL_DEV", "true")
    monkeypatch.setenv("MEDIBOT_ADMIN_PASSWORD", "test-admin-password")
    monkeypatch.setenv(
        "MEDIBOT_ADMIN_SESSION_SECRET",
        "test-only-session-signing-secret-with-enough-entropy",
    )
    unauthenticated_client = TestClient(
        app,
        client=("127.0.0.1", 43120),
    )

    response = unauthenticated_client.get("/admin/resources/")

    assert response.status_code == 200


def test_admin_is_directly_available_to_loopback_without_password(monkeypatch):
    monkeypatch.setenv("MEDIBOT_ADMIN_ALLOW_REMOTE", "false")
    monkeypatch.setenv("MEDIBOT_ADMIN_LOCAL_DEV", "true")
    monkeypatch.delenv("MEDIBOT_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("MEDIBOT_ADMIN_SESSION_SECRET", raising=False)
    unauthenticated_client = TestClient(
        app,
        client=("127.0.0.1", 43120),
    )

    response = unauthenticated_client.get("/admin/resources/")

    assert response.status_code == 200
    auth_status = unauthenticated_client.get("/admin/resources/auth/status")
    assert auth_status.json() == {
        "configured": True,
        "authenticated": True,
        "login_required": False,
    }


def test_admin_requires_password_outside_local_dev_mode(monkeypatch):
    monkeypatch.setenv("MEDIBOT_ADMIN_ALLOW_REMOTE", "false")
    monkeypatch.setenv("MEDIBOT_ADMIN_LOCAL_DEV", "false")
    monkeypatch.setenv("MEDIBOT_ADMIN_PASSWORD", "test-admin-password")
    monkeypatch.setenv(
        "MEDIBOT_ADMIN_SESSION_SECRET",
        "test-only-session-signing-secret-with-enough-entropy",
    )
    client_without_session = TestClient(
        app,
        client=("127.0.0.1", 43120),
    )

    response = client_without_session.get("/admin/resources/")

    assert response.status_code == 401


def test_admin_login_rejects_wrong_password(client):
    response = client.post(
        "/admin/resources/auth/login",
        json={"password": "incorrect-password"},
    )

    assert response.status_code == 401
    assert "medibot_admin_session" not in response.headers.get("set-cookie", "")
    assert client.get("/admin/resources/").status_code == 200


def test_admin_rejects_cross_origin_state_changes(client):
    response = client.post(
        "/admin/resources/auth/login",
        headers={"Origin": "https://attacker.example"},
        json={"password": "test-admin-password"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Cross-origin admin requests are not allowed."


def test_admin_login_issues_http_only_session_cookie(client):
    response = client.post(
        "/admin/resources/auth/login",
        json={"password": "test-admin-password"},
    )

    cookie_header = response.headers["set-cookie"].lower()
    assert response.status_code == 200
    assert "httponly" in cookie_header
    assert "samesite=strict" in cookie_header
    assert "max-age=43200" in cookie_header


def test_admin_session_cookie_is_http_only_and_logout_clears_it(client):
    login_response = client.post(
        "/admin/resources/auth/login",
        json={"password": "test-admin-password"},
    )
    assert login_response.status_code == 200
    assert client.cookies.get("medibot_admin_session")

    response = client.post("/admin/resources/auth/logout")

    assert response.status_code == 200
    assert client.get("/admin/resources/").status_code == 200


def test_admin_rejects_tampered_session_cookie(client):
    client.cookies.clear()
    client.cookies.set("medibot_admin_session", "tampered")

    response = client.get("/admin/resources/")

    assert response.status_code == 200


def test_admin_rejects_remote_client_by_default(resource_paths, monkeypatch):
    monkeypatch.delenv("MEDIBOT_ADMIN_ALLOW_REMOTE", raising=False)

    remote_client = TestClient(
        app,
        client=("203.0.113.20", 43120),
    )

    response = remote_client.get("/admin/resources/")

    assert response.status_code == 403
    assert not resource_paths[0].exists()


def test_admin_can_explicitly_allow_remote_clients(resource_paths, monkeypatch):
    monkeypatch.setenv("MEDIBOT_ADMIN_ALLOW_REMOTE", "true")
    monkeypatch.setenv("MEDIBOT_ADMIN_PASSWORD", "test-admin-password")
    monkeypatch.setenv(
        "MEDIBOT_ADMIN_SESSION_SECRET",
        "test-only-session-signing-secret-with-enough-entropy",
    )

    remote_client = TestClient(
        app,
        client=("203.0.113.20", 43120),
    )

    login_response = remote_client.post(
        "/admin/resources/auth/login",
        json={"password": "test-admin-password"},
    )
    response = remote_client.get("/admin/resources/")

    assert login_response.status_code == 200
    assert response.status_code == 200
    assert resource_paths[0].is_dir()


def test_remote_admin_requires_a_valid_session(monkeypatch):
    monkeypatch.setenv("MEDIBOT_ADMIN_ALLOW_REMOTE", "true")
    monkeypatch.setenv("MEDIBOT_ADMIN_PASSWORD", "test-admin-password")
    monkeypatch.setenv(
        "MEDIBOT_ADMIN_SESSION_SECRET",
        "test-only-session-signing-secret-with-enough-entropy",
    )
    remote_client = TestClient(
        app,
        client=("203.0.113.20", 43120),
    )

    auth_status = remote_client.get("/admin/resources/auth/status")
    response = remote_client.get("/admin/resources/")

    assert auth_status.json() == {
        "configured": True,
        "authenticated": False,
        "login_required": True,
    }
    assert response.status_code == 401


def test_remote_admin_requires_login_even_from_loopback_proxy(monkeypatch):
    monkeypatch.setenv("MEDIBOT_ADMIN_ALLOW_REMOTE", "true")
    monkeypatch.setenv("MEDIBOT_ADMIN_PASSWORD", "test-admin-password")
    monkeypatch.setenv(
        "MEDIBOT_ADMIN_SESSION_SECRET",
        "test-only-session-signing-secret-with-enough-entropy",
    )
    proxy_client = TestClient(
        app,
        client=("127.0.0.1", 43120),
    )

    auth_status = proxy_client.get("/admin/resources/auth/status")
    response = proxy_client.get("/admin/resources/")

    assert auth_status.json() == {
        "configured": True,
        "authenticated": False,
        "login_required": True,
    }
    assert response.status_code == 401


def test_remote_client_is_rejected_before_filesystem_writes(
    resource_paths,
    monkeypatch,
):
    monkeypatch.delenv("MEDIBOT_ADMIN_ALLOW_REMOTE", raising=False)

    remote_client = TestClient(
        app,
        client=("203.0.113.20", 43120),
    )

    response = remote_client.post(
        "/admin/resources/upload",
        files={"file": ("guide.txt", b"valid", "text/plain")},
    )

    assert response.status_code == 403
    assert not resource_paths[0].exists()
    assert not resource_paths[1].exists()
    assert not resource_paths[2].exists()
