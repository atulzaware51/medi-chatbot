"""Request and response schemas for Medibot chat."""

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    """Validate a user's chat question."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Question to answer using the indexed knowledge base.",
    )

class SourceReference(BaseModel):
    """Reference to a retrieved document passage."""

    id: str
    source: str
    page: int | None = None
    chunk_id: str | None = None


class ChatResponse(BaseModel):
    """Structured response returned by Medibot."""

    conversation_id: str
    question: str
    answer: str
    sources: list[SourceReference] = Field(default_factory=list)
