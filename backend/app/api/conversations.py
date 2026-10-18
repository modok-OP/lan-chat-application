from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Conversation, ConversationMember, Message, User
from app.db.session import get_db
from app.schemas.auth import AuthStatusResponse
from app.schemas.attachments import AttachmentResponse
from app.schemas.conversations import (
    DirectConversationCreate,
    GroupConversationCreate,
    GroupConversationUpdate,
    AddGroupMemberRequest,
    TransferOwnershipRequest,
    ConversationResponse,
    MemberSummary,
    MarkReadRequest,
    MarkReadResponse,
)
from app.schemas.messages import (
    MessageCreate,
    MessageResponse,
    PaginatedMessagesResponse,
    SearchMessagesResponse,
    ReplySummary,
    serialize_reactions,
)
from app.services.attachment_service import AttachmentService
from app.services.conversation_service import ConversationService
from app.services.message_service import MessageService
from app.services.presence_service import connection_manager

router = APIRouter(prefix="/conversations", tags=["Conversations"])


def serialize_conversation(conv: Conversation, unread_count: int = 0) -> ConversationResponse:
    """Format Conversation entity into ConversationResponse schema."""
    members_summary = []
    for m in conv.members:
        if m.user:
            members_summary.append(
                MemberSummary(
                    user_id=m.user.id,
                    username=m.user.username,
                    display_name=m.user.display_name,
                    role=m.role,
                    is_active=m.is_active,
                    joined_at=m.joined_at,
                    last_read_message_id=m.last_read_message_id,
                )
            )
    return ConversationResponse(
        id=conv.id,
        type=conv.type,
        name=conv.name,
        created_by=conv.created_by,
        direct_key=conv.direct_key,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        members=members_summary,
        unread_count=unread_count,
    )


def serialize_message(msg: Message) -> MessageResponse:
    """Format Message entity into MessageResponse schema."""
    atts = [
        AttachmentResponse.model_validate(a)
        for a in (msg.attachments or [])
    ]
    reply_to_summary = None
    if getattr(msg, "reply_to", None):
        reply_to_summary = ReplySummary(
            id=msg.reply_to.id,
            sender_username=msg.reply_to.sender.username if msg.reply_to.sender else None,
            sender_display_name=msg.reply_to.sender.display_name if msg.reply_to.sender else None,
            content=msg.reply_to.content if msg.reply_to.deleted_at is None else "[Message deleted]",
            message_type=msg.reply_to.message_type,
        )
    elif msg.reply_to_message_id:
        reply_to_summary = ReplySummary(
            id=msg.reply_to_message_id,
            sender_username=None,
            sender_display_name=None,
            content="[Replied message]",
            message_type="text",
        )

    reactions_summary = serialize_reactions(getattr(msg, "reactions", []))

    return MessageResponse(
        id=msg.id,
        conversation_id=msg.conversation_id,
        sender_id=msg.sender_id,
        sender_username=msg.sender.username if msg.sender else None,
        sender_display_name=msg.sender.display_name if msg.sender else None,
        client_message_id=msg.client_message_id,
        message_type=msg.message_type,
        content=msg.content,
        reply_to_message_id=msg.reply_to_message_id,
        reply_to=reply_to_summary,
        reactions=reactions_summary,
        created_at=msg.created_at,
        edited_at=msg.edited_at,
        deleted_at=msg.deleted_at,
        attachments=atts,
    )



async def broadcast_conversation_event(
    db: AsyncSession,
    conversation_id: int,
    system_msg: Optional[Message] = None,
    extra_user_ids: Optional[List[int]] = None,
):
    """Notify members of membership/metadata changes and broadcast system event messages."""
    members_stmt = select(ConversationMember.user_id).where(
        ConversationMember.conversation_id == conversation_id,
        ConversationMember.is_active == True,
    )
    active_uids = list((await db.execute(members_stmt)).scalars().all())

    all_notified_uids = set(active_uids)
    if extra_user_ids:
        all_notified_uids.update(extra_user_ids)

    # 1. Broadcast conversation.updated to all relevant users
    await connection_manager.broadcast_to_users(
        all_notified_uids,
        {
            "type": "conversation.updated",
            "payload": {"conversation_id": conversation_id},
        },
    )

    # 2. If a system message was generated, broadcast message.created to active members
    if system_msg:
        msg_payload = {
            "message_id": system_msg.id,
            "conversation_id": system_msg.conversation_id,
            "sender": None,
            "message_type": "system",
            "content": system_msg.content,
            "client_message_id": None,
            "reply_to_message_id": None,
            "reply_to": None,
            "reactions": [],
            "created_at": system_msg.created_at.isoformat(),
            "attachments": [],
        }
        await connection_manager.broadcast_to_users(
            active_uids,
            {
                "type": "message.created",
                "payload": msg_payload,
            },
        )


@router.get(
    "",
    response_model=List[ConversationResponse],
    status_code=status.HTTP_200_OK,
    summary="List Conversations",
    description="Retrieve all direct and group conversations visible to the current user.",
)
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[ConversationResponse]:
    conversations = await ConversationService.get_user_conversations(db, current_user.id)
    unread_counts = await ConversationService.get_unread_counts_for_user(db, current_user.id)
    return [serialize_conversation(c, unread_count=unread_counts.get(c.id, 0)) for c in conversations]


@router.post(
    "/direct",
    response_model=ConversationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get or Create Direct Chat",
    description="Get the existing direct conversation with a target user or create a new one.",
)
async def get_or_create_direct_chat(
    data: DirectConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    conv = await ConversationService.get_or_create_direct_conversation(
        db, current_user.id, data.target_user_id
    )
    return serialize_conversation(conv)


@router.post(
    "/groups",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Group Conversation",
    description="Create a new group conversation with a name and initial participants.",
)
async def create_group_chat(
    data: GroupConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    conv = await ConversationService.create_group_conversation(
        db, current_user.id, data.name, data.member_ids
    )
    sys_msg = await MessageService.create_system_message(
        db, conv.id, f"{current_user.display_name} created the group '{conv.name}'"
    )
    await broadcast_conversation_event(db, conv.id, system_msg=sys_msg)
    return serialize_conversation(conv)


@router.get(
    "/{conversation_id}",
    response_model=ConversationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Conversation Details",
    description="Fetch metadata and member list for a conversation.",
)
async def get_conversation_details(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    conv = await ConversationService.get_conversation_by_id(db, conversation_id, current_user.id)
    unread_counts = await ConversationService.get_unread_counts_for_user(db, current_user.id)
    return serialize_conversation(conv, unread_count=unread_counts.get(conv.id, 0))


@router.patch(
    "/{conversation_id}",
    response_model=ConversationResponse,
    status_code=status.HTTP_200_OK,
    summary="Rename Group",
    description="Rename a group conversation (owner or admin only).",
)
async def rename_group(
    conversation_id: int,
    data: GroupConversationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    conv = await ConversationService.rename_group(
        db, conversation_id, current_user.id, data.name
    )
    sys_msg = await MessageService.create_system_message(
        db, conversation_id, f"{current_user.display_name} renamed the group to '{data.name}'"
    )
    await broadcast_conversation_event(db, conversation_id, system_msg=sys_msg)
    return serialize_conversation(conv)


@router.post(
    "/{conversation_id}/members",
    response_model=MemberSummary,
    status_code=status.HTTP_200_OK,
    summary="Add Group Member",
    description="Add a user to a group (owner or admin only).",
)
async def add_member(
    conversation_id: int,
    data: AddGroupMemberRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemberSummary:
    member = await ConversationService.add_group_member(
        db, conversation_id, current_user.id, data.user_id, data.role
    )
    # Refresh user
    user = (await db.execute(select(User).where(User.id == member.user_id))).scalar_one()
    sys_msg = await MessageService.create_system_message(
        db, conversation_id, f"{current_user.display_name} added {user.display_name} to the group"
    )
    await broadcast_conversation_event(db, conversation_id, system_msg=sys_msg)
    return MemberSummary(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=member.role,
        is_active=member.is_active,
        joined_at=member.joined_at,
    )


@router.delete(
    "/{conversation_id}/members/{user_id}",
    response_model=AuthStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Remove Group Member",
    description="Remove a user from a group (owner or admin only).",
)
async def remove_member(
    conversation_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuthStatusResponse:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    target_name = user.display_name if user else f"User {user_id}"
    await ConversationService.remove_group_member(db, conversation_id, current_user.id, user_id)
    sys_msg = await MessageService.create_system_message(
        db, conversation_id, f"{current_user.display_name} removed {target_name} from the group"
    )
    await broadcast_conversation_event(db, conversation_id, system_msg=sys_msg, extra_user_ids=[user_id])
    return AuthStatusResponse(message="Member removed successfully")


@router.post(
    "/{conversation_id}/leave",
    response_model=AuthStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Leave Group",
    description="Leave a group conversation voluntarily.",
)
async def leave_group(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuthStatusResponse:
    await ConversationService.leave_group(db, conversation_id, current_user.id)
    sys_msg = await MessageService.create_system_message(
        db, conversation_id, f"{current_user.display_name} left the group"
    )
    await broadcast_conversation_event(db, conversation_id, system_msg=sys_msg, extra_user_ids=[current_user.id])
    return AuthStatusResponse(message="Left group successfully")


@router.post(
    "/{conversation_id}/transfer-ownership",
    response_model=ConversationResponse,
    status_code=status.HTTP_200_OK,
    summary="Transfer Group Ownership",
    description="Transfer group ownership to another active member (owner only).",
)
async def transfer_ownership(
    conversation_id: int,
    data: TransferOwnershipRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    new_owner = (await db.execute(select(User).where(User.id == data.new_owner_id))).scalar_one_or_none()
    new_owner_name = new_owner.display_name if new_owner else f"User {data.new_owner_id}"
    conv = await ConversationService.transfer_ownership(
        db, conversation_id, current_user.id, data.new_owner_id
    )
    sys_msg = await MessageService.create_system_message(
        db, conversation_id, f"{current_user.display_name} transferred group ownership to {new_owner_name}"
    )
    await broadcast_conversation_event(db, conversation_id, system_msg=sys_msg)
    return serialize_conversation(conv)


@router.post(
    "/{conversation_id}/read",
    response_model=MarkReadResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark Conversation Read",
    description="Update the current user's read marker for this conversation.",
)
async def mark_conversation_read_endpoint(
    conversation_id: int,
    data: Optional[MarkReadRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MarkReadResponse:
    target_id = data.last_read_message_id if data else None
    new_last_read = await ConversationService.mark_conversation_read(
        db, conversation_id, current_user.id, target_id
    )

    members_stmt = select(ConversationMember.user_id).where(
        ConversationMember.conversation_id == conversation_id,
        ConversationMember.is_active == True,
    )
    active_uids = list((await db.execute(members_stmt)).scalars().all())

    await connection_manager.broadcast_to_users(
        active_uids,
        {
            "type": "message.read.updated",
            "payload": {
                "conversation_id": conversation_id,
                "user_id": current_user.id,
                "last_read_message_id": new_last_read,
            },
        },
    )

    return MarkReadResponse(
        conversation_id=conversation_id,
        last_read_message_id=new_last_read,
        unread_count=0,
    )


@router.get(
    "/{conversation_id}/messages",
    response_model=PaginatedMessagesResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch Conversation Messages",
    description="Fetch paginated message history. Older messages can be fetched using ?before=<oldest_id>.",
)
async def get_messages(
    conversation_id: int,
    before: Optional[int] = Query(None, description="Fetch messages older than this message ID"),
    limit: int = Query(50, ge=1, le=100, description="Number of messages to retrieve"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedMessagesResponse:
    messages, has_more, oldest_id = await MessageService.get_conversation_messages(
        db, conversation_id, current_user.id, before_id=before, limit=limit
    )
    return PaginatedMessagesResponse(
        messages=[serialize_message(m) for m in messages],
        has_more=has_more,
        oldest_id=oldest_id,
    )


@router.get(
    "/{conversation_id}/messages/search",
    response_model=SearchMessagesResponse,
    status_code=status.HTTP_200_OK,
    summary="Search Messages in Conversation",
    description="Search message content within a specific conversation. Requires active membership.",
)
async def search_messages(
    conversation_id: int,
    q: str = Query(..., min_length=1, max_length=200, description="Search keyword or phrase"),
    limit: int = Query(50, ge=1, le=100, description="Max results to return"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SearchMessagesResponse:
    matches = await MessageService.search_conversation_messages(
        db, conversation_id, current_user.id, q, limit=limit
    )
    return SearchMessagesResponse(
        conversation_id=conversation_id,
        query=q,
        total_matches=len(matches),
        messages=[serialize_message(m) for m in matches],
    )



@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Post Message (REST)",
    description="Post a message to a conversation via REST API.",
)
async def post_message(
    conversation_id: int,
    data: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    msg = await MessageService.create_message(
        db=db,
        conversation_id=conversation_id,
        sender_id=current_user.id,
        content=data.content,
        client_message_id=data.client_message_id,
        reply_to_message_id=data.reply_to_message_id,
    )
    return serialize_message(msg)


@router.post(
    "/{conversation_id}/attachments",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload File Attachment",
    description="Upload a multipart file attachment. Persists file message and broadcasts message.created.",
)
async def upload_attachment(
    conversation_id: int,
    file: UploadFile = File(..., description="Multipart file attachment"),
    client_message_id: Optional[str] = Form(None, description="Optional client idempotency ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Save attachment, persist file message, and broadcast delivery to active conversation members."""
    msg, att = await AttachmentService.save_attachment(
        db=db,
        conversation_id=conversation_id,
        uploader_id=current_user.id,
        file=file,
        client_message_id=client_message_id,
    )

    # Broadcast message.created to active conversation members
    members_stmt = select(ConversationMember.user_id).where(
        ConversationMember.conversation_id == conversation_id,
        ConversationMember.is_active == True,
    )
    active_uids = list((await db.execute(members_stmt)).scalars().all())

    att_payload = {
        "id": att.id,
        "message_id": msg.id,
        "original_filename": att.original_filename,
        "mime_type": att.mime_type,
        "size_bytes": att.size_bytes,
        "sha256": att.sha256,
        "uploaded_by": att.uploaded_by,
        "created_at": att.created_at.isoformat(),
        "download_url": f"/api/attachments/{att.id}/download",
    }

    broadcast_payload = {
        "message_id": msg.id,
        "conversation_id": msg.conversation_id,
        "sender": {
            "id": current_user.id,
            "username": current_user.username,
            "display_name": current_user.display_name,
        },
        "message_type": "file",
        "content": msg.content,
        "client_message_id": msg.client_message_id,
        "reply_to_message_id": None,
        "reply_to": None,
        "reactions": [],
        "created_at": msg.created_at.isoformat(),
        "attachments": [att_payload],
    }

    await connection_manager.broadcast_to_users(
        active_uids,
        {
            "type": "message.created",
            "payload": broadcast_payload,
        },
    )

    return serialize_message(msg)
