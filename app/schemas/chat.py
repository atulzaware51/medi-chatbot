
"""Request and response schemas for Medibot chat."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Validate a user's chat question and conversation ID."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Question to answer using the indexed knowledge base.",
    )
    thread_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Unique conversation ID used to restore chat history.",
    )


class SourceReference(BaseModel):
    """Reference to a retrieved document passage."""

    id: str
    source: str
    page: int | None = None
    chunk_id: str | None = None


class ChatResponse(BaseModel):
    """Structured response returned by Medibot."""

    question: str
    answer: str
    sources: list[SourceReference] = Field(default_factory=list)


class ConversationResponse(BaseModel):
    """Conversation metadata returned only to its authenticated owner."""

    id: str
    thread_id: str
    title: str
    created_at: str
    updated_at: str


class ConversationMessage(BaseModel):
    """Persisted message belonging to an owned conversation."""

    role: str
    content: str
    sources: list[SourceReference] = Field(default_factory=list)
    created_at: str
