"""Tests for explicitly supplied, owner-authorized workflow history."""

import app.graph.workflow as workflow


def test_workflow_uses_only_explicitly_supplied_history(monkeypatch):
    calls = []

    def fake_ask_medibot(question, conversation_history=None):
        calls.append(
            {
                "question": question,
                "history": conversation_history or [],
            }
        )
        return {
            "question": question,
            "answer": f"Mock answer to: {question}",
            "sources": [],
        }

    monkeypatch.setattr(workflow, "ask_medibot", fake_ask_medibot)
    history = [
        {"role": "user", "content": "What is Medibot?"},
        {"role": "assistant", "content": "It is an information tool."},
    ]

    workflow.run_medibot_graph(
        "What did I ask first?",
        conversation_history=history,
    )
    workflow.run_medibot_graph("Separate question")

    assert calls == [
        {
            "question": "What did I ask first?",
            "history": history,
        },
        {
            "question": "Separate question",
            "history": [],
        },
    ]
