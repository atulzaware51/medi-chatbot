
"""Automated tests for the Medibot chat API."""

from fastapi.testclient import TestClient
from uuid import uuid4

from app.main import app
import app.api.chat as chat_module


client = TestClient(app)


def create_authenticated_conversation():
    response = client.post(
        "/auth/register",
        json={
            "name": "Test User",
            "email": f"{uuid4().hex}@example.test",
            "password": "test-password-long-enough",
        },
    )
    assert response.status_code == 201
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    conversation = client.post("/chat/conversations/", headers=headers)
    assert conversation.status_code == 201
    return headers, conversation.json()["thread_id"]


def test_chat_returns_answer_and_sources(monkeypatch):
    """A valid question returns an answer and source references."""

    def fake_run_medibot_graph(question, thread_id="default"):
        return {
            "question": question,
            "answer": (
                "Medibot retrieves information from "
                "user-provided documents. [S1]"
            ),
            "sources": [
                {
                    "id": "S1",
                    "source": "medibot_demo.txt",
                    "page": None,
                    "chunk_id": "chunk-1",
                }
            ],
        }

    monkeypatch.setattr(
        chat_module,
        "run_medibot_graph",
        fake_run_medibot_graph,
    )

    headers, thread_id = create_authenticated_conversation()
    response = client.post(
        "/chat/",
        headers=headers,
        json={
            "question": "What is Medibot designed to do?",
            "thread_id": thread_id,
        },
    )

    assert response.status_code == 200

    body = response.json()
    assert body["question"] == "What is Medibot designed to do?"
    assert "Medibot retrieves information" in body["answer"]
    assert body["sources"][0]["source"] == "medibot_demo.txt"


def test_chat_rejects_empty_question():
    """An empty question fails request validation."""

    headers, thread_id = create_authenticated_conversation()
    response = client.post(
        "/chat/",
        headers=headers,
        json={
            "question": "",
            "thread_id": thread_id,
        },
    )

    assert response.status_code == 422


def test_chat_handles_service_validation_error(monkeypatch):
    """A service validation error returns HTTP 400."""

    def fake_run_medibot_graph(question, thread_id="default"):
        raise ValueError("Question cannot be empty.")

    monkeypatch.setattr(
        chat_module,
        "run_medibot_graph",
        fake_run_medibot_graph,
    )

    headers, thread_id = create_authenticated_conversation()
    response = client.post(
        "/chat/",
        headers=headers,
        json={
            "question": "   ",
            "thread_id": thread_id,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Question cannot be empty."
