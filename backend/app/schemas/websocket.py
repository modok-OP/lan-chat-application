from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.schemas.auth import UserResponse
from app.schemas.messages import MessageResponse


class WebSocketEnvelope(BaseModel):
    """Base envelope for all WebSocket messages."""

    type: str = Field(..., description="Event type identifier")
    request_id: Optional[str] = Field(None, description="Client request ID for request-response tracking")
    payload: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Event data")


class MessageSendPayload(BaseModel):
    """Payload for client 'message.send' event."""

    conversation_id: int = Field(..., description="Target conversation ID")
    content: str = Field(..., min_length=1, max_length=10000, description="Message text content")
    client_message_id: Optional[str] = Field(None, max_length=100, description="Client idempotency key")
    reply_to_message_id: Optional[int] = Field(None, description="Optional parent message ID")


class MessageAckPayload(BaseModel):
    """Payload for server 'message.ack' confirmation."""

    message_id: int
    conversation_id: int
    client_message_id: Optional[str] = None
    created_at: str


class PresenceChangedPayload(BaseModel):
    """Payload for 'presence.changed' event."""

    user_id: int
    status: str  # 'online' or 'offline'
