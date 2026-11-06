"""Stateless answer workflow; owned conversation history comes from the DB."""

from typing import Any, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from app.rag.answer_service import ask_medibot


class MedibotState(TypedDict, total=False):
    """Input and result for one answer generation request."""

    question: str
    answer: str
    sources: list[dict[str, Any]]
    messages: list[AnyMessage]


def answer_question(state: MedibotState) -> dict[str, Any]:
    """Answer one question using only the explicitly supplied history."""
    messages = state.get("messages", [])
    conversation_history = []

    for message in messages[:-1]:
        if isinstance(message, HumanMessage):
            role = "user"
        elif isinstance(message, AIMessage):
            role = "assistant"
        else:
            continue
        conversation_history.append(
            {"role": role, "content": str(message.content)}
        )

    result = ask_medibot(
        state["question"],
        conversation_history=conversation_history,
    )
    return {
        "answer": result["answer"],
        "sources": result.get("sources", []),
        "messages": [AIMessage(content=result["answer"])],
    }


def build_medibot_graph():
    """Compile the stateless answer-generation graph."""
    graph = StateGraph(MedibotState)
    graph.add_node("answer_question", answer_question)
    graph.add_edge(START, "answer_question")
    graph.add_edge("answer_question", END)
    return graph.compile()


medibot_graph = build_medibot_graph()


def run_medibot_graph(
    question: str,
    conversation_history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Run one answer turn with history already authorized by the caller."""
    question = question.strip()
    if not question:
        raise ValueError("Question cannot be empty.")

    messages: list[AnyMessage] = []
    for item in (conversation_history or [])[-100:]:
        role = item.get("role")
        content = item.get("content")
        if role == "user" and isinstance(content, str):
            messages.append(HumanMessage(content=content))
        elif role == "assistant" and isinstance(content, str):
            messages.append(AIMessage(content=content))
    messages.append(HumanMessage(content=question))

    result = medibot_graph.invoke(
        {
            "question": question,
            "messages": messages,
        }
    )
    return {
        "question": question,
        "answer": result["answer"],
        "sources": result.get("sources", []),
    }
