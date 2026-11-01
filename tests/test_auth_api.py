"""Authentication, conversation ownership, and persistence tests."""

from uuid import uuid4

from fastapi.testclient import TestClient

import app.auth as auth_module
import app.api.chat as chat_module
from app.main import app


client = TestClient(app)


def register_user(name: str = "Test User") -> tuple[dict[str, str], str]:
    response = client.post(
        "/auth/register",
        json={
            "name": name,
            "email": f"{uuid4().hex}@example.test",
            "password": "a-long-test-password",
        },
    )
    assert response.status_code == 201
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, response.json()["user"]["id"]


def test_registration_login_me_and_logout():
    email = f"{uuid4().hex}@example.test"
    payload = {
        "name": "Medibot User",
        "email": email,
        "password": "a-long-test-password",
    }

    registration = client.post("/auth/register", json=payload)

    assert registration.status_code == 201
    token = registration.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/auth/me", headers=headers).json()["email"] == email

    login = client.post(
        "/auth/login",
        json={"email": email.upper(), "password": payload["password"]},
    )
    assert login.status_code == 200
    assert login.json()["user"]["id"] == registration.json()["user"]["id"]

    logout = client.post("/auth/logout", headers=headers)
    assert logout.status_code == 204
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_auth_rejects_duplicate_accounts_and_invalid_passwords():
    email = f"{uuid4().hex}@example.test"
    payload = {
        "name": "Medibot User",
        "email": email,
        "password": "a-long-test-password",
    }
    assert client.post("/auth/register", json=payload).status_code == 201
    assert client.post("/auth/register", json=payload).status_code == 409
    assert client.post(
        "/auth/register",
        json={**payload, "email": "not-an-email"},
    ).status_code == 422
    assert client.post(
        "/auth/register",
        json={**payload, "email": f"{uuid4().hex}@example.test", "password": "short"},
    ).status_code == 422
    assert client.post(
        "/auth/login",
        json={"email": email, "password": "incorrect-password"},
    ).status_code == 401


def test_login_rate_limit_returns_retry_after(monkeypatch):
    monkeypatch.setattr(auth_module, "AUTH_RATE_LIMIT_ATTEMPTS", 2)
    rate_limited_client = TestClient(app, client=("192.0.2.88", 43120))

    for _ in range(2):
        response = rate_limited_client.post(
            "/auth/login",
            json={
                "email": f"{uuid4().hex}@example.test",
                "password": "invalid-password",
            },
        )
        assert response.status_code == 401

    limited = rate_limited_client.post(
        "/auth/login",
        json={
            "email": f"{uuid4().hex}@example.test",
            "password": "invalid-password",
        },
    )
    assert limited.status_code == 429
    assert limited.headers["retry-after"]


def test_chat_requires_a_valid_access_token():
    response = client.post(
        "/chat/",
        json={"question": "What is Medibot?", "thread_id": "unowned-thread"},
    )
    assert response.status_code == 401

    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401


def test_users_cannot_read_or_append_to_another_users_conversation(monkeypatch):
    owner_headers, _ = register_user("Owner")
    other_headers, _ = register_user("Other")
    created = client.post("/chat/conversations/", headers=owner_headers)
    conversation_id = created.json()["id"]

    monkeypatch.setattr(
        chat_module,
        "run_medibot_graph",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Graph must not run for a non-owner")
        ),
    )

    assert client.get(
        f"/chat/conversations/{conversation_id}/messages",
        headers=other_headers,
    ).status_code == 404
    assert client.post(
        "/chat/",
        headers=other_headers,
        json={"question": "Read this", "thread_id": conversation_id},
    ).status_code == 404
    assert client.delete(
        f"/chat/conversations/{conversation_id}",
        headers=other_headers,
    ).status_code == 404
    assert client.get(
        "/chat/conversations/",
        headers=other_headers,
    ).json() == []


def test_messages_persist_and_owner_can_delete_conversation(monkeypatch):
    headers, _ = register_user()
    conversation = client.post("/chat/conversations/", headers=headers).json()

    monkeypatch.setattr(
        chat_module,
        "run_medibot_graph",
        lambda question, thread_id: {
            "question": question,
            "answer": "Grounded test response.",
            "sources": [
                {"id": "S1", "source": "guide.txt", "chunk_id": "c1"}
            ],
        },
    )

    response = client.post(
        "/chat/",
        headers=headers,
        json={
            "question": "What does the guide say?",
            "thread_id": conversation["thread_id"],
        },
    )
    assert response.status_code == 200

    persisted = client.get(
        f"/chat/conversations/{conversation['id']}/messages",
        headers=headers,
    )
    assert persisted.status_code == 200
    assert [message["role"] for message in persisted.json()] == [
        "user",
        "assistant",
    ]
    assert persisted.json()[1]["sources"][0]["id"] == "S1"

    removed = client.delete(
        f"/chat/conversations/{conversation['id']}",
        headers=headers,
    )
    assert removed.status_code == 204
    assert client.get(
        f"/chat/conversations/{conversation['id']}/messages",
        headers=headers,
    ).status_code == 404
