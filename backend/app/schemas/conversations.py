from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class DirectConversationCreate(BaseModel):
    """Payload to get or create a direct conversation."""

    target_user_id: int = Field(..., description="ID of the user to chat with")


class GroupConversationCreate(BaseModel):
    """Payload to create a new group conversation."""

    name: str = Field(..., min_length=1, max_length=100, description="Name of the group")
    member_ids: List[int] = Field(
        default_factory=list,
        description="List of initial user IDs to add as members",
    )


class GroupConversationUpdate(BaseModel):
    """Payload to rename a group conversation."""

    name: str = Field(..., min_length=1, max_length=100, description="New name of the group")


class AddGroupMemberRequest(BaseModel):
    """Payload to add a user to a group."""

    user_id: int = Field(..., description="User ID to add to the group")
    role: str = Field(default="member", description="Role to assign ('member' or 'admin')")


class TransferOwnershipRequest(BaseModel):
    """Payload to transfer group ownership to another member."""

    new_owner_id: int = Field(..., description="User ID of the new owner")


class MemberSummary(BaseModel):
    """Summary of a user membership in a conversation."""

    user_id: int
    username: str
    display_name: str
    role: str
    is_active: bool
    joined_at: datetime
    last_read_message_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class MarkReadRequest(BaseModel):
    """Payload to mark messages in a conversation as read."""

    last_read_message_id: Optional[int] = Field(None, description="Latest message ID read (defaults to newest message)")


class MarkReadResponse(BaseModel):
    """Response returned when marking a conversation as read."""

    conversation_id: int
    last_read_message_id: int
    unread_count: int = 0


class ConversationResponse(BaseModel):
    """Conversation metadata and participant details."""

    id: int
    type: str  # 'direct' or 'group'
    name: Optional[str] = None
    created_by: Optional[int] = None
    direct_key: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    members: List[MemberSummary] = []
    unread_count: int = 0

    model_config = ConfigDict(from_attributes=True)

