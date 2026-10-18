from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppException
from app.db.models import Conversation, Message, MessageReaction
from app.schemas.messages import serialize_reactions
from app.services.permission_service import PermissionService


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def message_options():
    """Consistent eager-loading strategy for Message entity graphs."""
    return (
        selectinload(Message.sender),
        selectinload(Message.attachments),
        selectinload(Message.reactions).selectinload(MessageReaction.user),
        selectinload(Message.reply_to).selectinload(Message.sender),
    )


class MessageService:
    """Service handling message persistence, search, reactions, and paginated history retrieval."""

    @staticmethod
    async def create_message(
        db: AsyncSession,
        conversation_id: int,
        sender_id: int,
        content: str,
        client_message_id: Optional[str] = None,
        message_type: str = "text",
        reply_to_message_id: Optional[int] = None,
    ) -> Message:
        """Persist a new message after verifying sender membership and reply references."""
        await PermissionService.get_active_membership(db, conversation_id, sender_id)

        clean_content = content.strip()
        if not clean_content:
            raise AppException("Message content cannot be empty")

        # Validate that reply_to_message_id belongs to the same conversation
        valid_reply_to_id: Optional[int] = None
        if reply_to_message_id is not None:
            parent_stmt = select(Message.id).where(
                Message.id == reply_to_message_id,
                Message.conversation_id == conversation_id,
                Message.deleted_at == None,
            )
            valid_reply_to_id = (await db.execute(parent_stmt)).scalar_one_or_none()

        # Idempotency check: avoid duplicate message if retried with same client_message_id
        if client_message_id:
            existing_stmt = (
                select(Message)
                .options(*message_options())
                .where(
                    Message.conversation_id == conversation_id,
                    Message.sender_id == sender_id,
                    Message.client_message_id == client_message_id,
                )
            )
            existing_msg = (await db.execute(existing_stmt)).scalar_one_or_none()
            if existing_msg:
                return existing_msg

        now = utc_now()
        new_msg = Message(
            conversation_id=conversation_id,
            sender_id=sender_id,
            client_message_id=client_message_id,
            message_type=message_type,
            content=clean_content,
            reply_to_message_id=valid_reply_to_id,
            created_at=now,
        )
        db.add(new_msg)

        # Bump conversation updated_at
        conv_stmt = select(Conversation).where(Conversation.id == conversation_id)
        conv = (await db.execute(conv_stmt)).scalar_one_or_none()
        if conv:
            conv.updated_at = now

        await db.commit()

        # Load full message entity with relations
        stmt = (
            select(Message)
            .options(*message_options())
            .where(Message.id == new_msg.id)
        )
        return (await db.execute(stmt)).scalar_one()

    @staticmethod
    async def create_system_message(
        db: AsyncSession,
        conversation_id: int,
        content: str,
    ) -> Message:
        """Persist a system-generated event message (sender_id is null)."""
        clean_content = content.strip()
        now = utc_now()
        new_msg = Message(
            conversation_id=conversation_id,
            sender_id=None,
            client_message_id=None,
            message_type="system",
            content=clean_content,
            created_at=now,
        )
        db.add(new_msg)

        # Bump conversation updated_at
        conv_stmt = select(Conversation).where(Conversation.id == conversation_id)
        conv = (await db.execute(conv_stmt)).scalar_one_or_none()
        if conv:
            conv.updated_at = now

        await db.commit()

        stmt = (
            select(Message)
            .options(*message_options())
            .where(Message.id == new_msg.id)
        )
        return (await db.execute(stmt)).scalar_one()

    @staticmethod
    async def get_conversation_messages(
        db: AsyncSession,
        conversation_id: int,
        user_id: int,
        before_id: Optional[int] = None,
        limit: int = 50,
    ) -> Tuple[List[Message], bool, Optional[int]]:
        """Fetch paginated message history in chronological order."""
        await PermissionService.get_active_membership(db, conversation_id, user_id)

        clamped_limit = max(1, min(limit, 100))

        query = (
            select(Message)
            .options(*message_options())
            .where(
                Message.conversation_id == conversation_id,
                Message.deleted_at == None,
            )
        )

        if before_id:
            query = query.where(Message.id < before_id)

        query = query.order_by(Message.id.desc()).limit(clamped_limit + 1)
        results = (await db.execute(query)).scalars().all()

        has_more = len(results) > clamped_limit
        paged_messages = list(results[:clamped_limit])

        oldest_id = paged_messages[-1].id if paged_messages else None

        # Return chronologically (oldest to newest)
        paged_messages.reverse()
        return paged_messages, has_more, oldest_id

    @staticmethod
    async def search_conversation_messages(
        db: AsyncSession,
        conversation_id: int,
        user_id: int,
        query_text: str,
        limit: int = 50,
    ) -> List[Message]:
        """Search message text content in a conversation respecting user membership."""
        await PermissionService.get_active_membership(db, conversation_id, user_id)

        clean_q = query_text.strip()
        if not clean_q:
            return []

        clamped_limit = max(1, min(limit, 100))
        stmt = (
            select(Message)
            .options(*message_options())
            .where(
                Message.conversation_id == conversation_id,
                Message.deleted_at == None,
                Message.content.ilike(f"%{clean_q}%"),
            )
            .order_by(Message.id.desc())
            .limit(clamped_limit)
        )
        return list((await db.execute(stmt)).scalars().all())

    @staticmethod
    async def toggle_reaction(
        db: AsyncSession,
        message_id: int,
        user_id: int,
        emoji: str,
    ) -> Tuple[Message, List[Any], bool]:
        """Toggle an emoji reaction on a message for the user.

        Returns: (Message, List[ReactionSummary], is_added: bool)
        """
        clean_emoji = emoji.strip()
        if not clean_emoji or len(clean_emoji) > 16:
            raise AppException("Invalid emoji: must be between 1 and 16 characters", status_code=400)

        # 1. Fetch message and verify it exists
        stmt = (
            select(Message)
            .where(Message.id == message_id, Message.deleted_at == None)
        )
        msg = (await db.execute(stmt)).scalar_one_or_none()
        if not msg:
            raise AppException("Message not found", status_code=404)

        # 2. Verify user has active membership in the conversation
        await PermissionService.get_active_membership(db, msg.conversation_id, user_id)

        # 3. Check if reaction exists for (message_id, user_id, emoji)
        r_stmt = select(MessageReaction).where(
            MessageReaction.message_id == message_id,
            MessageReaction.user_id == user_id,
            MessageReaction.emoji == clean_emoji,
        )
        existing_reaction = (await db.execute(r_stmt)).scalar_one_or_none()

        if existing_reaction:
            await db.delete(existing_reaction)
            is_added = False
        else:
            new_reaction = MessageReaction(
                message_id=message_id,
                user_id=user_id,
                emoji=clean_emoji,
                created_at=utc_now(),
            )
            db.add(new_reaction)
            is_added = True

        await db.commit()

        # 4. Fetch all reactions for this message with user relation loaded
        r_list_stmt = (
            select(MessageReaction)
            .options(selectinload(MessageReaction.user))
            .where(MessageReaction.message_id == message_id)
        )
        fresh_reactions = list((await db.execute(r_list_stmt)).scalars().all())
        return msg, serialize_reactions(fresh_reactions), is_added
