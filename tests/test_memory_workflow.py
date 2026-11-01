
"""Tests for Medibot's persistent LangGraph conversation memory."""

from uuid import uuid4

import app.graph.workflow as workflow


def test_same_thread_receives_previous_conversation(monkeypatch):
    """A second question in the same thread receives the first turn."""

    calls = []

    def fake_ask_medibot(question, conversation_history=None):
        history = conversation_history or []
        calls.append(
            {
                "question": question,
                "history": history,
            }
        )
        return {
            "question": question,
            "answer": f"Mock answer to: {question}",
            "sources": [],
        }

    monkeypatch.setattr(workflow, "ask_medibot", fake_ask_medibot)

    thread_id = f"memory-test-{uuid4().hex}"

    workflow.run_medibot_graph(
        "What is Medibot?",
        thread_id=thread_id,
    )
    workflow.run_medibot_graph(
        "What did I ask first?",
        thread_id=thread_id,
    )

    assert len(calls) == 2
    assert calls[0]["history"] == []
    assert any(
        item["role"] == "user" and item["content"] == "What is Medibot?"
        for item in calls[1]["history"]
    )
    assert any(
        item["role"] == "assistant"
        and item["content"] == "Mock answer to: What is Medibot?"
        for item in calls[1]["history"]
    )


def test_different_threads_do_not_share_history(monkeypatch):
    """A new thread starts without another thread's messages."""

    calls = []

    def fake_ask_medibot(question, conversation_history=None):
        calls.append(conversation_history or [])
        return {
            "question": question,
            "answer": f"Mock answer to: {question}",
            "sources": [],
        }

    monkeypatch.setattr(workflow, "ask_medibot", fake_ask_medibot)

    workflow.run_medibot_graph(
        "Private conversation A",
        thread_id=f"thread-a-{uuid4().hex}",
    )
    workflow.run_medibot_graph(
        "Separate conversation B",
        thread_id=f"thread-b-{uuid4().hex}",
    )

    assert len(calls) == 2
    assert calls[0] == []
    assert calls[1] == []
