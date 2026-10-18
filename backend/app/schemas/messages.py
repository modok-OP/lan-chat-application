from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict

from app.schemas.attachments import AttachmentResponse


class MessageCreate(BaseModel):
    """Payload to post a text message."""

    content: str = Field(..., min_length=1, max_length=10000, description="Message text content")
    client_message_id: Optional[str] = Field(None, max_length=100, description="Idempotency key")
    reply_to_message_id: Optional[int] = Field(None, description="Optional parent message ID")


class ReplySummary(BaseModel):
    """Summary of a referenced parent message in a reply."""

    id: int
    sender_username: Optional[str] = None
    sender_display_name: Optional[str] = None
    content: str
    message_type: str = "text"


class ReactionSummary(BaseModel):
    """Aggregated emoji reactions on a message."""

    emoji: str
    count: int
    user_ids: List[int] = Field(default_factory=list)
    usernames: List[str] = Field(default_factory=list)


def serialize_reactions(reactions) -> List[ReactionSummary]:
    """Helper to group database MessageReaction models into ReactionSummary items."""
    reaction_map: dict[str, dict] = {}
    for r in (reactions or []):
        if r.emoji not in reaction_map:
            reaction_map[r.emoji] = {
                "emoji": r.emoji,
                "count": 0,
                "user_ids": [],
                "usernames": [],
            }
        reaction_map[r.emoji]["count"] += 1
        reaction_map[r.emoji]["user_ids"].append(r.user_id)
        uname = r.user.username if getattr(r, "user", None) else f"user_{r.user_id}"
        reaction_map[r.emoji]["usernames"].append(uname)
    return [ReactionSummary(**data) for data in reaction_map.values()]


class ReactionToggleRequest(BaseModel):
    """Payload to toggle an emoji reaction on a message."""

    emoji: str = Field(..., min_length=1, max_length=16, description="Emoji character/string")


class ReactionToggleResponse(BaseModel):
    """Response returned when toggling an emoji reaction."""

    message_id: int
    conversation_id: int
    action: str  # "added" or "removed"
    reactions: List[ReactionSummary]


class MessageResponse(BaseModel):
    """Message representation."""

    id: int
    conversation_id: int
    sender_id: Optional[int] = None
    sender_username: Optional[str] = None
    sender_display_name: Optional[str] = None
    client_message_id: Optional[str] = None
    message_type: str = "text"
    content: str
    reply_to_message_id: Optional[int] = None
    reply_to: Optional[ReplySummary] = None
    reactions: List[ReactionSummary] = Field(default_factory=list)
    created_at: datetime
    edited_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    attachments: List[AttachmentResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)



class PaginatedMessagesResponse(BaseModel):
    """Paginated conversation message history."""

    messages: List[MessageResponse]
    has_more: bool
    oldest_id: Optional[int] = None


class SearchMessagesResponse(BaseModel):
    """Result of searching messages in a conversation."""

    conversation_id: int
    query: str
    total_matches: int
    messages: List[MessageResponse]

