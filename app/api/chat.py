"""Authenticated chat and conversation-history endpoints."""

import logging
import os
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.auth import (
    AuthContext,
    enforce_rate_limit,
    get_auth_context,
    purge_expired_data,
    require_csrf,
)
from app.db import get_db
from app.graph.workflow import run_medibot_graph
from app.models import Conversation, ConversationMessage, utc_now
from app.schemas.chat import ChatRequest, ChatResponse, SourceReference

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["Chat"])
CHAT_RATE_LIMIT = int(os.getenv("MEDIBOT_CHAT_RATE_LIMIT", "30"))
MAX_MESSAGES_PER_CONVERSATION = 100


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationMessageResponse(BaseModel):
    role: str
    content: str
    sources: list[SourceReference] = Field(default_factory=list)
    created_at: datetime


class ConversationResponse(ConversationSummary):
    messages: list[ConversationMessageResponse]


class NewConversationResponse(ConversationSummary):
    pass


def _enforce_chat_limit(db: Session, user_id: str) -> None:
    enforce_rate_limit(
        db,
        scope="chat:user",
        identity=user_id,
        limit=CHAT_RATE_LIMIT,
        window_seconds=60,
    )


def _get_owned_conversation(
    db: Session,
    conversation_id: str,
    owner_id: str,
    *,
    include_messages: bool = False,
) -> Conversation:
    statement = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.owner_id == owner_id,
    )
    if include_messages:
        statement = statement.options(selectinload(Conversation.messages))
    conversation = db.scalar(statement)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )
    return conversation


@router.post(
    "/conversations",
    response_model=NewConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> Conversation:
    """Create an empty conversation with a server-generated identifier."""
    purge_expired_data(db)
    _enforce_chat_limit(db, auth.user.id)
    conversation = Conversation(id=str(uuid4()), owner_id=auth.user.id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[Conversation]:
    """List only the current user's conversations."""
    purge_expired_data(db)
    return list(
        db.scalars(
            select(Conversation)
            .where(Conversation.owner_id == auth.user.id)
            .order_by(Conversation.updated_at.desc())
        )
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
)
def get_conversation(
    conversation_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> Conversation:
    """Restore messages only when the conversation belongs to the caller."""
    purge_expired_data(db)
    _enforce_chat_limit(db, auth.user.id)
    return _get_owned_conversation(
        db,
        conversation_id,
        auth.user.id,
        include_messages=True,
    )


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conversation(
    conversation_id: str,
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> Response:
    """Delete an owned conversation and all of its messages."""
    purge_expired_data(db)
    _enforce_chat_limit(db, auth.user.id)
    conversation = _get_owned_conversation(db, conversation_id, auth.user.id)
    db.delete(conversation)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ChatResponse,
)
def send_message(
    conversation_id: str,
    payload: ChatRequest,
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Generate an answer and persist the turn under its authenticated owner."""
    question = payload.question.strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be empty.",
        )

    purge_expired_data(db)
    _enforce_chat_limit(db, auth.user.id)
    conversation = _get_owned_conversation(
        db,
        conversation_id,
        auth.user.id,
    )
    stored_messages = list(
        db.scalars(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation.id)
            .order_by(ConversationMessage.id.desc())
            .limit(MAX_MESSAGES_PER_CONVERSATION)
        )
    )
    stored_messages.reverse()
    history = [
        {"role": message.role, "content": message.content}
        for message in stored_messages
        if message.role in {"user", "assistant"}
    ]

    try:
        result = run_medibot_graph(
            question,
            conversation_history=history,
        )
    except FileNotFoundError as exc:
        logger.error(
            "Knowledge base unavailable while processing chat (%s).",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The knowledge base is not ready. Ingest documents first.",
        ) from exc
    except Exception as exc:
        logger.error("Chat request failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Medibot could not process the question. Check the server logs.",
        ) from exc

    response_at = utc_now()
    sources = result.get("sources", [])
    conversation.messages.extend(
        [
            ConversationMessage(
                role="user",
                content=question,
                sources=[],
                created_at=response_at,
            ),
            ConversationMessage(
                role="assistant",
                content=result["answer"],
                sources=sources,
                created_at=response_at,
            ),
        ]
    )
    conversation.updated_at = response_at
    if not history:
        normalized_question = " ".join(question.split())
        conversation.title = normalized_question[:157]
        if len(normalized_question) > 157:
            conversation.title += "..."
    db.commit()
    old_messages = list(
        db.scalars(
            select(ConversationMessage.id)
            .where(ConversationMessage.conversation_id == conversation.id)
            .order_by(ConversationMessage.id.desc())
            .offset(MAX_MESSAGES_PER_CONVERSATION)
        )
    )
    if old_messages:
        db.execute(
            delete(ConversationMessage)
            .where(ConversationMessage.id.in_(old_messages))
            .execution_options(synchronize_session=False)
        )
        db.commit()

    return ChatResponse(
        conversation_id=conversation.id,
        question=result["question"],
        answer=result["answer"],
        sources=sources,
    )
