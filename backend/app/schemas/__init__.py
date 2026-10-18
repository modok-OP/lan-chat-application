"""Pydantic schemas for request and response validation."""

from app.schemas.health import HealthResponse
from app.schemas.errors import ErrorDetail, ErrorResponse
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    UserResponse,
    AuthStatusResponse,
)
from app.schemas.conversations import (
    DirectConversationCreate,
    GroupConversationCreate,
    GroupConversationUpdate,
    AddGroupMemberRequest,
    MemberSummary,
    ConversationResponse,
)
from app.schemas.messages import (
    MessageCreate,
    MessageResponse,
    PaginatedMessagesResponse,
)
from app.schemas.attachments import AttachmentResponse

__all__ = [
    "HealthResponse",
    "ErrorDetail",
    "ErrorResponse",
    "RegisterRequest",
    "LoginRequest",
    "UserResponse",
    "AuthStatusResponse",
    "DirectConversationCreate",
    "GroupConversationCreate",
    "GroupConversationUpdate",
    "AddGroupMemberRequest",
    "MemberSummary",
    "ConversationResponse",
    "MessageCreate",
    "MessageResponse",
    "PaginatedMessagesResponse",
    "AttachmentResponse",
]
