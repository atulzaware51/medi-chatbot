
"""Chat API endpoints for Medibot."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import get_current_user
from app.conversations import (
    create_conversation,
    delete_owned_conversation,
    get_conversation_messages,
    get_owned_conversation,
    list_conversations,
    save_exchange,
)
from app.graph.workflow import run_medibot_graph
from app.memory.checkpointer import get_checkpointer
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationMessage,
    ConversationResponse,
)

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    user: Annotated[dict[str, str], Depends(get_current_user)],
) -> ChatResponse:
    """Answer a question through the LangGraph workflow."""

    try:
        if get_owned_conversation(user["id"], request.thread_id) is None:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found.",
            )

        result = run_medibot_graph(
            request.question,
            thread_id=request.thread_id,
        )
        if not save_exchange(
            user["id"],
            request.thread_id,
            result["question"],
            result["answer"],
            result.get("sources", []),
        ):
            raise HTTPException(
                status_code=404,
                detail="Conversation not found.",
            )

        return ChatResponse(
            question=result["question"],
            answer=result["answer"],
            sources=result.get("sources", []),
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="The knowledge base is not ready. Ingest documents first.",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Medibot could not process the question. Check the server logs.",
        ) from exc


@router.post("/conversations/", response_model=ConversationResponse, status_code=201)
def new_conversation(
    user: Annotated[dict[str, str], Depends(get_current_user)],
) -> ConversationResponse:
    return ConversationResponse(**create_conversation(user["id"]))


@router.get("/conversations/", response_model=list[ConversationResponse])
def conversations(
    user: Annotated[dict[str, str], Depends(get_current_user)],
) -> list[ConversationResponse]:
    return [
        ConversationResponse(
            thread_id=item["id"],
            **item,
        )
        for item in list_conversations(user["id"])
    ]


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[ConversationMessage],
)
def conversation_messages(
    conversation_id: str,
    user: Annotated[dict[str, str], Depends(get_current_user)],
) -> list[ConversationMessage]:
    if get_owned_conversation(user["id"], conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return [
        ConversationMessage(**message)
        for message in get_conversation_messages(user["id"], conversation_id)
    ]


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: str,
    user: Annotated[dict[str, str], Depends(get_current_user)],
) -> None:
    if get_owned_conversation(user["id"], conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    try:
        get_checkpointer().delete_thread(conversation_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Conversation could not be deleted safely.",
        ) from exc

    if not delete_owned_conversation(user["id"], conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")