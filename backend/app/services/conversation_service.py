from datetime import datetime, timezone
from typing import List, Optional, Dict
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import (
    AppException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.core.logging import logger
from app.db.models import Conversation, ConversationMember, Message, User
from app.services.permission_service import PermissionService


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ConversationService:
    """Business operations for conversations and membership lifecycle."""

    @staticmethod
    async def get_or_create_direct_conversation(
        db: AsyncSession,
        current_user_id: int,
        target_user_id: int,
    ) -> Conversation:
        """Find or create a direct conversation between two users with guaranteed uniqueness."""
        if current_user_id == target_user_id:
            raise AppException("Cannot create a direct conversation with yourself")

        # Verify target user exists and is active
        target_stmt = select(User).where(User.id == target_user_id, User.is_active == True)
        target_user = (await db.execute(target_stmt)).scalar_one_or_none()
        if target_user is None:
            raise NotFoundException("Target user not found or inactive")

        # Deterministic unique key for this pair
        low_id, high_id = min(current_user_id, target_user_id), max(current_user_id, target_user_id)
        direct_key = f"{low_id}:{high_id}"

        # Check existing conversation
        conv_stmt = (
            select(Conversation)
            .options(
                selectinload(Conversation.members).selectinload(ConversationMember.user)
            )
            .where(Conversation.direct_key == direct_key)
        )
        existing_conv = (await db.execute(conv_stmt)).scalar_one_or_none()

        if existing_conv:
            # Ensure both members are active
            changed = False
            for m in existing_conv.members:
                if not m.is_active:
                    m.is_active = True
                    changed = True
            if changed:
                existing_conv.updated_at = utc_now()
                await db.commit()
            return existing_conv

        # Create new direct conversation
        now = utc_now()
        new_conv = Conversation(
            type="direct",
            direct_key=direct_key,
            created_by=current_user_id,
            created_at=now,
            updated_at=now,
        )
        db.add(new_conv)
        await db.flush()

        # Add both users as participants
        m1 = ConversationMember(
            conversation_id=new_conv.id,
            user_id=current_user_id,
            role="participant",
            is_active=True,
            joined_at=now,
        )
        m2 = ConversationMember(
            conversation_id=new_conv.id,
            user_id=target_user_id,
            role="participant",
            is_active=True,
            joined_at=now,
        )
        db.add_all([m1, m2])
        await db.commit()

        # Re-query with eager relationships loaded
        return await ConversationService.get_conversation_by_id(db, new_conv.id, current_user_id)

    @staticmethod
    async def create_group_conversation(
        db: AsyncSession,
        creator_id: int,
        name: str,
        member_ids: List[int],
    ) -> Conversation:
        """Create a new group conversation with the creator as owner."""
        clean_name = name.strip()
        if not clean_name:
            raise AppException("Group name cannot be empty")

        now = utc_now()
        new_group = Conversation(
            type="group",
            name=clean_name,
            created_by=creator_id,
            created_at=now,
            updated_at=now,
        )
        db.add(new_group)
        await db.flush()

        # Creator is owner
        owner_member = ConversationMember(
            conversation_id=new_group.id,
            user_id=creator_id,
            role="owner",
            is_active=True,
            joined_at=now,
        )
        db.add(owner_member)

        # Add initial members (filter duplicates & creator)
        unique_member_ids = set(member_ids) - {creator_id}
        if unique_member_ids:
            # Validate that users exist and are active
            users_stmt = select(User).where(User.id.in_(unique_member_ids), User.is_active == True)
            found_users = (await db.execute(users_stmt)).scalars().all()
            for user in found_users:
                db.add(
                    ConversationMember(
                        conversation_id=new_group.id,
                        user_id=user.id,
                        role="member",
                        is_active=True,
                        joined_at=now,
                    )
                )

        await db.commit()
        logger.info("Group conversation created: '%s' (id=%d) by user %d", clean_name, new_group.id, creator_id)
        return await ConversationService.get_conversation_by_id(db, new_group.id, creator_id)

    @staticmethod
    async def get_user_conversations(
        db: AsyncSession,
        user_id: int,
    ) -> List[Conversation]:
        """Fetch all conversations where user is an active participant."""
        stmt = (
            select(Conversation)
            .join(ConversationMember, Conversation.id == ConversationMember.conversation_id)
            .options(
                selectinload(Conversation.members).selectinload(ConversationMember.user)
            )
            .where(
                ConversationMember.user_id == user_id,
                ConversationMember.is_active == True,
            )
            .order_by(Conversation.updated_at.desc())
        )
        results = await db.execute(stmt)
        return list(results.scalars().all())

    @staticmethod
    async def get_conversation_by_id(
        db: AsyncSession,
        conversation_id: int,
        user_id: int,
    ) -> Conversation:
        """Fetch conversation details after verifying active membership."""
        await PermissionService.get_active_membership(db, conversation_id, user_id)

        stmt = (
            select(Conversation)
            .options(
                selectinload(Conversation.members).selectinload(ConversationMember.user)
            )
            .where(Conversation.id == conversation_id)
        )
        conv = (await db.execute(stmt)).scalar_one_or_none()
        if conv is None:
            raise NotFoundException("Conversation not found")
        return conv

    @staticmethod
    async def rename_group(
        db: AsyncSession,
        conversation_id: int,
        user_id: int,
        new_name: str,
    ) -> Conversation:
        """Rename a group (requires owner or admin role)."""
        await PermissionService.require_group_admin_or_owner(db, conversation_id, user_id)

        clean_name = new_name.strip()
        if not clean_name:
            raise AppException("Group name cannot be empty")

        conv_stmt = select(Conversation).where(Conversation.id == conversation_id)
        conv = (await db.execute(conv_stmt)).scalar_one_or_none()
        if conv is None:
            raise NotFoundException("Conversation not found")

        conv.name = clean_name
        conv.updated_at = utc_now()
        await db.commit()
        return await ConversationService.get_conversation_by_id(db, conversation_id, user_id)

    @staticmethod
    async def add_group_member(
        db: AsyncSession,
        conversation_id: int,
        actor_id: int,
        target_user_id: int,
        role: str = "member",
    ) -> ConversationMember:
        """Add or reactivate a member in a group (requires owner or admin role)."""
        await PermissionService.require_group_admin_or_owner(db, conversation_id, actor_id)

        # Check target user
        user_stmt = select(User).where(User.id == target_user_id, User.is_active == True)
        target_user = (await db.execute(user_stmt)).scalar_one_or_none()
        if target_user is None:
            raise NotFoundException("Target user not found or inactive")

        # Check existing membership row
        m_stmt = select(ConversationMember).where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id == target_user_id,
        )
        existing_m = (await db.execute(m_stmt)).scalar_one_or_none()

        now = utc_now()
        if existing_m:
            if existing_m.is_active:
                if existing_m.role == role:
                    raise ConflictException("User is already an active member of this group")
                # Role update requires owner
                actor_m = await PermissionService.get_active_membership(db, conversation_id, actor_id)
                if actor_m.role != "owner":
                    raise ForbiddenException("Only the owner can modify member roles", code="INSUFFICIENT_PERMISSIONS")
                existing_m.role = role
                member = existing_m
            else:
                existing_m.is_active = True
                existing_m.role = role
                existing_m.joined_at = now
                member = existing_m
        else:
            member = ConversationMember(
                conversation_id=conversation_id,
                user_id=target_user_id,
                role=role,
                is_active=True,
                joined_at=now,
            )
            db.add(member)

        # Bump conversation updated_at
        conv_stmt = select(Conversation).where(Conversation.id == conversation_id)
        conv = (await db.execute(conv_stmt)).scalar_one_or_none()
        if conv:
            conv.updated_at = now

        await db.commit()
        return member

    @staticmethod
    async def remove_group_member(
        db: AsyncSession,
        conversation_id: int,
        actor_id: int,
        target_user_id: int,
    ) -> None:
        """Remove a member from a group (requires owner or admin role)."""
        actor_membership = await PermissionService.require_group_admin_or_owner(
            db, conversation_id, actor_id
        )

        target_stmt = select(ConversationMember).where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id == target_user_id,
            ConversationMember.is_active == True,
        )
        target_membership = (await db.execute(target_stmt)).scalar_one_or_none()
        if target_membership is None:
            raise NotFoundException("Target member not found in this group")

        # Protections: cannot remove owner
        if target_membership.role == "owner":
            raise ForbiddenException("Cannot remove the group owner")

        # Admin cannot remove another admin (only owner can)
        if target_membership.role == "admin" and actor_membership.role != "owner":
            raise ForbiddenException("Only the owner can remove group admins")

        target_membership.is_active = False

        # Bump updated_at
        conv_stmt = select(Conversation).where(Conversation.id == conversation_id)
        conv = (await db.execute(conv_stmt)).scalar_one_or_none()
        if conv:
            conv.updated_at = utc_now()

        await db.commit()

    @staticmethod
    async def leave_group(
        db: AsyncSession,
        conversation_id: int,
        user_id: int,
    ) -> None:
        """Voluntarily leave a group conversation."""
        membership = await PermissionService.get_active_membership(db, conversation_id, user_id)

        conv_stmt = select(Conversation).where(Conversation.id == conversation_id)
        conv = (await db.execute(conv_stmt)).scalar_one_or_none()
        if conv is None or conv.type != "group":
            raise AppException("Can only leave group conversations")

        # Owner cannot leave if other active members exist
        if membership.role == "owner":
            other_active_stmt = select(ConversationMember).where(
                ConversationMember.conversation_id == conversation_id,
                ConversationMember.user_id != user_id,
                ConversationMember.is_active == True,
            )
            other_active = (await db.execute(other_active_stmt)).scalars().all()
            if other_active:
                raise ForbiddenException(
                    "Group owner cannot leave while other members remain. Transfer ownership first.",
                    code="OWNER_CANNOT_LEAVE",
                )

        membership.is_active = False
        conv.updated_at = utc_now()
        await db.commit()

    @staticmethod
    async def transfer_ownership(
        db: AsyncSession,
        conversation_id: int,
        current_owner_id: int,
        new_owner_id: int,
    ) -> Conversation:
        owner_membership = await PermissionService.get_active_membership(db, conversation_id, current_owner_id)
        if owner_membership.role != "owner":
            raise ForbiddenException("Only the group owner can transfer ownership", code="INSUFFICIENT_PERMISSIONS")

        if current_owner_id == new_owner_id:
            raise AppException("Cannot transfer ownership to yourself")

        target_membership = await PermissionService.get_active_membership(db, conversation_id, new_owner_id)

        owner_membership.role = "admin"
        target_membership.role = "owner"

        conv_stmt = select(Conversation).where(Conversation.id == conversation_id)
        conv = (await db.execute(conv_stmt)).scalar_one()
        conv.updated_at = utc_now()
        await db.commit()
        return await ConversationService.get_conversation_by_id(db, conversation_id, current_owner_id)

    @staticmethod
    async def get_unread_counts_for_user(
        db: AsyncSession,
        user_id: int,
    ) -> Dict[int, int]:
        """Calculate unread message count per conversation for a given user."""
        stmt = (
            select(
                Message.conversation_id,
                func.count(Message.id).label("unread_count"),
            )
            .join(
                ConversationMember,
                Message.conversation_id == ConversationMember.conversation_id,
            )
            .where(
                ConversationMember.user_id == user_id,
                ConversationMember.is_active == True,
                Message.id > func.coalesce(ConversationMember.last_read_message_id, 0),
                or_(Message.sender_id == None, Message.sender_id != user_id),
            )
            .group_by(Message.conversation_id)
        )
        rows = (await db.execute(stmt)).all()
        return {conv_id: count for conv_id, count in rows}

    @staticmethod
    async def mark_conversation_read(
        db: AsyncSession,
        conversation_id: int,
        user_id: int,
        last_read_message_id: Optional[int] = None,
    ) -> int:
        """Update last_read_message_id for an active conversation member."""
        member = await PermissionService.get_active_membership(db, conversation_id, user_id)

        target_msg_id = last_read_message_id
        if target_msg_id is None:
            # Query newest message ID in conversation
            max_stmt = select(func.max(Message.id)).where(Message.conversation_id == conversation_id)
            latest_id = (await db.execute(max_stmt)).scalar()
            target_msg_id = latest_id or 0

        # Only advance forward, never move backward
        if target_msg_id > (member.last_read_message_id or 0):
            member.last_read_message_id = target_msg_id
            await db.commit()

        return member.last_read_message_id or 0
