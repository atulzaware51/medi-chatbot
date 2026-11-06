
"""Grounding, citation, conflict, and medical safety tests."""

from types import SimpleNamespace

import pytest

import app.rag.answer_service as service


def test_no_evidence_returns_safe_response_without_calling_llm(monkeypatch):
    monkeypatch.setattr(service, "search_knowledge_base", lambda *a, **kw: [])
    monkeypatch.setattr(
        service,
        "get_llm",
        lambda: pytest.fail("LLM must not be called without evidence or history"),
    )

    result = service.ask_medibot("What is the exact population of Mars?")

    assert result["sources"] == []
    assert "couldn't find relevant supporting information" in result["answer"]


@pytest.mark.parametrize(
    "question",
    [
        "I have chest pain. What should I do?",
        "Someone cannot breathe.",
        "There is severe bleeding.",
        "Could this be an overdose?",
    ],
)
def test_emergency_questions_return_immediate_guidance(monkeypatch, question):
    monkeypatch.setattr(
        service,
        "search_knowledge_base",
        lambda *a, **kw: pytest.fail("Emergency check should run first"),
    )
    monkeypatch.setattr(
        service,
        "get_llm",
        lambda: pytest.fail("Emergency response must not depend on the LLM"),
    )

    result = service.ask_medibot(question)

    assert result["sources"] == []
    assert "emergency services" in result["answer"].lower()
    assert "now" in result["answer"].lower()


@pytest.mark.parametrize(
    "question",
    [
        "Do I have osteoporosis?",
        "What is causing these symptoms?",
        "Should I stop my medication?",
        "What dose should I take?",
        "Can I combine these medicines?",
    ],
)
def test_personal_diagnosis_and_medication_decisions_are_not_generated(
    monkeypatch,
    question,
):
    monkeypatch.setattr(
        service,
        "search_knowledge_base",
        lambda *a, **kw: pytest.fail("A personal treatment decision must not be generated"),
    )
    monkeypatch.setattr(
        service,
        "get_llm",
        lambda: pytest.fail("A personal treatment decision must not call the LLM"),
    )

    result = service.ask_medibot(question)

    assert result["sources"] == []
    assert "can't diagnose" in result["answer"]
    assert "pharmacist" in result["answer"]


def test_source_labels_match_returned_source_references(monkeypatch):
    monkeypatch.setattr(
        service,
        "search_knowledge_base",
        lambda *a, **kw: [
            {
                "source": "fractures.txt",
                "page": 2,
                "chunk_id": "chunk-1",
                "content": "A fracture is a broken bone.",
            },
            {
                "source": "bone_health.txt",
                "page": 1,
                "chunk_id": "chunk-2",
                "content": "Bone health includes maintaining strong bones.",
            },
        ],
    )

    prompts = []

    class FakeLLM:
        def invoke(self, prompt):
            prompts.append(prompt)
            return SimpleNamespace(
                content="A fracture is a broken bone. [S1] [S99]"
            )

    monkeypatch.setattr(service, "get_llm", lambda: FakeLLM())

    result = service.ask_medibot("What is a fracture?")

    assert result["sources"][0]["id"] == "S1"
    assert result["sources"][0]["source"] == "fractures.txt"
    assert result["sources"][1]["id"] == "S2"
    assert "[S1]" in result["answer"]
    assert "[S99]" not in result["answer"]
    assert "A fracture is a broken bone." in prompts[0]


def test_conflicting_documents_are_both_in_prompt(monkeypatch):
    monkeypatch.setattr(
        service,
        "search_knowledge_base",
        lambda *a, **kw: [
            {
                "source": "document_a.txt",
                "content": "Document A states the treatment lasts five days.",
            },
            {
                "source": "document_b.txt",
                "content": "Document B states the treatment lasts ten days.",
            },
        ],
    )

    prompts = []

    class FakeLLM:
        def invoke(self, prompt):
            prompts.append(prompt)
            return SimpleNamespace(
                content=(
                    "The documents disagree: [S1] states five days, "
                    "while [S2] states ten days."
                )
            )

    monkeypatch.setattr(service, "get_llm", lambda: FakeLLM())

    result = service.ask_medibot("How long does the treatment last?")

    assert len(result["sources"]) == 2
    assert "five days" in prompts[0]
    assert "ten days" in prompts[0]
    assert "documents conflict" in prompts[0].lower()
    assert "[S1]" in result["answer"]
    assert "[S2]" in result["answer"]


def test_follow_up_can_use_history_when_retrieval_is_empty(monkeypatch):
    monkeypatch.setattr(service, "search_knowledge_base", lambda *a, **kw: [])

    prompts = []

    class FakeLLM:
        def invoke(self, prompt):
            prompts.append(prompt)
            return SimpleNamespace(content="You previously said your name is Alex.")

    monkeypatch.setattr(service, "get_llm", lambda: FakeLLM())

    result = service.ask_medibot(
        "What is my name?",
        conversation_history=[
            {"role": "user", "content": "My name is Alex."},
            {"role": "assistant", "content": "Nice to meet you, Alex."},
        ],
    )

    assert "My name is Alex." in prompts[0]
    assert result["sources"] == []
    assert "Alex" in result["answer"]


def test_empty_question_is_rejected():
    with pytest.raises(ValueError, match="Question cannot be empty"):
        service.ask_medibot("   ")


def test_empty_llm_response_is_rejected(monkeypatch):
    monkeypatch.setattr(
        service,
        "search_knowledge_base",
        lambda *a, **kw: [
            {
                "source": "fractures.txt",
                "content": "A fracture is a broken bone.",
            }
        ],
    )

    class FakeLLM:
        def invoke(self, prompt):
            return SimpleNamespace(content="   ")

    monkeypatch.setattr(service, "get_llm", lambda: FakeLLM())

    with pytest.raises(RuntimeError, match="empty answer"):
        service.ask_medibot("What is a fracture?")

@pytest.mark.parametrize(
    "text",
    [
        "Calcium?especially dietary calcium?is important.",
        "Bone health improves with care.?S1??S2?",
        "A fracture is a broken bone. [S1]",
        "The patient has a fracture.",
    ],
)
def test_clean_answer_preserves_valid_unicode_and_citations(text):
    assert service._clean_answer_text(text) == text


def test_clean_answer_normalizes_unicode_whitespace():
    text = "Bone\u00a0health\u202fis important.\ufeff"
    assert service._clean_answer_text(text) == "Bone health is important."
