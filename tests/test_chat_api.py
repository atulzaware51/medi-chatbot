"""Authentication, ownership, retention, and chat API regression tests."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.api import chat as chat_module
from app.auth import SESSION_COOKIE, _digest
from app.db import SessionLocal
from app.main import app
from app.models import AuthSession, Conversation, ConversationMessage, utc_now


PASSWORD = "a-long-test-password-2026"


@pytest.fixture
def client():
    return TestClient(app)


def register(client, email="one@example.com", password=PASSWORD):
    response = client.post(
        "/auth/register",
        json={"email": email, "password": password},
    )
    assert response.status_code == 201
    return response.json()["csrf_token"]


def csrf_headers(token):
    return {"X-CSRF-Token": token}


def create_conversation(client, csrf_token):
    response = client.post(
        "/chat/conversations",
        headers=csrf_headers(csrf_token),
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_chat_requires_a_valid_account_session(client):
    response = client.post(
        "/chat/conversations",
        headers={"X-CSRF-Token": "irrelevant"},
    )
    assert response.status_code == 401


def test_register_login_and_restore_owned_chat(client, monkeypatch):
    csrf_token = register(client)
    conversation_id = create_conversation(client, csrf_token)
    calls = []

    def fake_run_medibot_graph(question, conversation_history=None):
        calls.append((question, conversation_history or []))
        return {
            "question": question,
            "answer": f"Mock answer to: {question}",
            "sources": [
                {
                    "id": "S1",
                    "source": "guide.txt",
                    "page": None,
                    "chunk_id": "chunk-1",
                }
            ],
        }

    monkeypatch.setattr(chat_module, "run_medibot_graph", fake_run_medibot_graph)
    first = client.post(
        f"/chat/conversations/{conversation_id}/messages",
        headers=csrf_headers(csrf_token),
        json={"question": "What is Medibot?"},
    )
    second = client.post(
        f"/chat/conversations/{conversation_id}/messages",
        headers=csrf_headers(csrf_token),
        json={"question": "What did I ask first?"},
    )

    assert first.status_code == 200
    assert first.json()["conversation_id"] == conversation_id
    assert first.json()["sources"][0]["source"] == "guide.txt"
    assert second.status_code == 200
    assert calls[0][1] == []
    assert calls[1][1] == [
        {"role": "user", "content": "What is Medibot?"},
        {"role": "assistant", "content": "Mock answer to: What is Medibot?"},
    ]

    restored = client.get(f"/chat/conversations/{conversation_id}")
    assert restored.status_code == 200
    assert [item["role"] for item in restored.json()["messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert restored.json()["title"] == "What is Medibot?"


def test_login_uses_generic_failure_and_issues_session(client):
    register(client)
    client.post("/auth/logout", headers=csrf_headers(client.cookies.get("medibot_csrf")))

    invalid = client.post(
        "/auth/login",
        json={"email": "missing@example.com", "password": PASSWORD},
    )
    assert invalid.status_code == 401
    assert invalid.json()["detail"] == "Invalid email or password."

    valid = client.post(
        "/auth/login",
        json={"email": "ONE@example.com", "password": PASSWORD},
    )
    assert valid.status_code == 200
    assert valid.cookies.get(SESSION_COOKIE)
    assert valid.json()["csrf_token"]


def test_rejects_missing_or_invalid_csrf_token(client):
    csrf_token = register(client)
    conversation_id = create_conversation(client, csrf_token)

    missing = client.delete(f"/chat/conversations/{conversation_id}")
    invalid = client.delete(
        f"/chat/conversations/{conversation_id}",
        headers=csrf_headers("wrong-token"),
    )
    assert missing.status_code == 403
    assert invalid.status_code == 403


def test_users_cannot_read_or_change_each_others_conversations(client):
    owner_client = TestClient(app)
    attacker_client = TestClient(app)
    owner_csrf = register(owner_client, "owner@example.com")
    attacker_csrf = register(attacker_client, "attacker@example.com")
    conversation_id = create_conversation(owner_client, owner_csrf)

    assert attacker_client.get(
        f"/chat/conversations/{conversation_id}"
    ).status_code == 404
    assert attacker_client.delete(
        f"/chat/conversations/{conversation_id}",
        headers=csrf_headers(attacker_csrf),
    ).status_code == 404
    assert attacker_client.post(
        f"/chat/conversations/{conversation_id}/messages",
        headers=csrf_headers(attacker_csrf),
        json={"question": "Can I access this?"},
    ).status_code == 404


def test_conversation_deletion_removes_messages(client, monkeypatch):
    csrf_token = register(client)
    conversation_id = create_conversation(client, csrf_token)
    monkeypatch.setattr(
        chat_module,
        "run_medibot_graph",
        lambda question, conversation_history=None: {
            "question": question,
            "answer": "Answer.",
            "sources": [],
        },
    )
    client.post(
        f"/chat/conversations/{conversation_id}/messages",
        headers=csrf_headers(csrf_token),
        json={"question": "Question"},
    )

    response = client.delete(
        f"/chat/conversations/{conversation_id}",
        headers=csrf_headers(csrf_token),
    )
    assert response.status_code == 204
    assert client.get(f"/chat/conversations/{conversation_id}").status_code == 404
    with SessionLocal() as db:
        assert db.query(ConversationMessage).count() == 0


def test_expired_sessions_are_rejected(client):
    register(client)
    session_token = client.cookies.get(SESSION_COOKIE)
    with SessionLocal() as db:
        record = db.query(AuthSession).filter_by(token_hash=_digest(session_token)).one()
        record.expires_at = utc_now() - timedelta(seconds=1)
        db.commit()

    response = client.get("/auth/me")
    assert response.status_code == 401


def test_old_conversations_are_removed_by_retention_policy(client):
    csrf_token = register(client)
    conversation_id = create_conversation(client, csrf_token)
    with SessionLocal() as db:
        conversation = db.get(Conversation, conversation_id)
        conversation.updated_at = utc_now() - timedelta(days=31)
        db.commit()

    response = client.get("/chat/conversations")
    assert response.status_code == 200
    assert response.json() == []


def test_deleting_account_removes_sessions_and_conversations(client):
    csrf_token = register(client)
    conversation_id = create_conversation(client, csrf_token)
    response = client.request(
        "DELETE",
        "/auth/me",
        headers=csrf_headers(csrf_token),
        json={"password": PASSWORD},
    )
    assert response.status_code == 200
    assert client.get(f"/chat/conversations/{conversation_id}").status_code == 401
    with SessionLocal() as db:
        assert db.query(Conversation).count() == 0
        assert db.query(AuthSession).count() == 0


def test_chat_requests_are_rate_limited(client, monkeypatch):
    csrf_token = register(client)
    conversation_id = create_conversation(client, csrf_token)
    monkeypatch.setattr(chat_module, "CHAT_RATE_LIMIT", 2)

    assert client.get(f"/chat/conversations/{conversation_id}").status_code == 200
    blocked = client.get(f"/chat/conversations/{conversation_id}")
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == "60"
