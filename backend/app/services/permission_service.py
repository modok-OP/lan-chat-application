from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.errors import ForbiddenException, NotFoundException
from app.db.models import Conversation, ConversationMember


class PermissionService:
    """Reusable authorization service enforcing conversation access rules."""

    @staticmethod
    async def get_active_membership(
        db: AsyncSession,
        conversation_id: int,
        user_id: int,
    ) -> ConversationMember:
        """Verify that user is an active participant in the conversation."""
        # Check if conversation exists
        conv_stmt = select(Conversation).where(Conversation.id == conversation_id)
        conv = (await db.execute(conv_stmt)).scalar_one_or_none()
        if conv is None:
            raise NotFoundException("Conversation not found")

        stmt = select(ConversationMember).where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id == user_id,
            ConversationMember.is_active == True,
        )
        membership = (await db.execute(stmt)).scalar_one_or_none()
        if membership is None:
            raise ForbiddenException(
                "You are not an active member of this conversation",
                code="CONVERSATION_ACCESS_DENIED",
            )
        return membership

    @staticmethod
    async def require_group_admin_or_owner(
        db: AsyncSession,
        conversation_id: int,
        user_id: int,
    ) -> ConversationMember:
        """Verify that user is an active owner or admin of a group conversation."""
        membership = await PermissionService.get_active_membership(db, conversation_id, user_id)

        conv_stmt = select(Conversation).where(Conversation.id == conversation_id)
        conv = (await db.execute(conv_stmt)).scalar_one_or_none()

        if conv and conv.type != "group":
            raise ForbiddenException("Group operations can only be performed on group conversations")

        if membership.role not in ("owner", "admin"):
            raise ForbiddenException(
                "Only group owners and admins can perform this action",
                code="INSUFFICIENT_PERMISSIONS",
            )

        return membership
