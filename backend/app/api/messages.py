"""Message-level operations: reactions, edits, and deletions."""

from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import ConversationMember, User
from app.db.session import get_db
from app.schemas.messages import ReactionToggleRequest, ReactionToggleResponse
from app.services.message_service import MessageService
from app.services.presence_service import connection_manager

router = APIRouter(prefix="/messages", tags=["Messages"])


@router.post(
    "/{message_id}/reactions",
    response_model=ReactionToggleResponse,
    status_code=status.HTTP_200_OK,
    summary="Toggle Message Emoji Reaction",
    description="Add or remove an emoji reaction on a message. Broadcasts message.reaction.updated to conversation members.",
)
async def toggle_reaction(
    message_id: int,
    data: ReactionToggleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReactionToggleResponse:
    """Toggle emoji reaction on message and broadcast update event to conversation members."""
    msg, reactions, is_added = await MessageService.toggle_reaction(
        db, message_id, current_user.id, data.emoji
    )

    # Broadcast message.reaction.updated to active conversation members
    members_stmt = select(ConversationMember.user_id).where(
        ConversationMember.conversation_id == msg.conversation_id,
        ConversationMember.is_active == True,
    )
    active_uids = list((await db.execute(members_stmt)).scalars().all())

    await connection_manager.broadcast_to_users(
        active_uids,
        {
            "type": "message.reaction.updated",
            "payload": {
                "conversation_id": msg.conversation_id,
                "message_id": msg.id,
                "reactions": [r.model_dump() for r in reactions],
            },
        },
    )

    return ReactionToggleResponse(
        message_id=msg.id,
        conversation_id=msg.conversation_id,
        action="added" if is_added else "removed",
        reactions=reactions,
    )
