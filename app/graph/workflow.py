
"""LangGraph workflow for Medibot with persistent conversation state."""

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage, AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.memory.checkpointer import get_checkpointer
from app.rag.answer_service import ask_medibot


class MedibotState(TypedDict, total=False):
    """State saved and restored for each conversation."""

    question: str
    answer: str
    sources: list[dict[str, Any]]
    messages: Annotated[list[AnyMessage], add_messages]


def answer_question(state: MedibotState) -> dict[str, Any]:
    """Answer the question using documents and prior conversation turns."""

    messages = state.get("messages", [])

    # The latest message is the current question.
    previous_messages = messages[:-1]

    conversation_history = []

    for message in previous_messages:
        if isinstance(message, HumanMessage):
            role = "user"
        elif isinstance(message, AIMessage):
            role = "assistant"
        else:
            continue

        conversation_history.append(
            {
                "role": role,
                "content": str(message.content),
            }
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
    """Build a graph with persistent SQLite checkpoints."""

    graph = StateGraph(MedibotState)
    graph.add_node("answer_question", answer_question)
    graph.add_edge(START, "answer_question")
    graph.add_edge("answer_question", END)

    return graph.compile(checkpointer=get_checkpointer())


medibot_graph = build_medibot_graph()


def run_medibot_graph(
    question: str,
    thread_id: str = "default",
) -> dict[str, Any]:
    """Run the graph using the checkpoint for the specified conversation."""

    question = question.strip()
    thread_id = thread_id.strip()

    if not question:
        raise ValueError("Question cannot be empty.")

    if not thread_id:
        raise ValueError("Conversation ID cannot be empty.")

    result = medibot_graph.invoke(
        {
            "question": question,
            "messages": [HumanMessage(content=question)],
        },
        config={"configurable": {"thread_id": thread_id}},
    )

    return {
        "question": question,
        "answer": result["answer"],
        "sources": result.get("sources", []),
    }
