import hashlib
from pathlib import Path
import re
import secrets
from typing import Optional, Tuple
import uuid

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.errors import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
    PayloadTooLargeException,
)
from app.db.models import Attachment, Conversation, Message, utc_now
from app.services.permission_service import PermissionService


def sanitize_filename(filename: Optional[str]) -> str:
    """Sanitize display filename, stripping path traversal and dangerous characters."""
    if not filename or not filename.strip():
        return "attachment.bin"

    # Strip any directory separators and traversal characters
    clean = Path(filename).name

    # Remove non-printable or control characters (null bytes, newlines, etc.)
    clean = re.sub(r"[\x00-\x1f\x7f]", "", clean)

    # Strip leading/trailing dots and spaces
    clean = clean.strip(". ")

    if not clean:
        return "attachment.bin"

    # Truncate overly long filenames while preserving file extension
    if len(clean) > 255:
        p = Path(clean)
        stem = p.stem[:235]
        suffix = p.suffix[:15]
        clean = f"{stem}{suffix}"

    return clean


class AttachmentService:
    """Service handling file upload streaming, metadata tracking, and secure downloads."""

    @staticmethod
    async def save_attachment(
        db: AsyncSession,
        conversation_id: int,
        uploader_id: int,
        file: UploadFile,
        client_message_id: Optional[str] = None,
    ) -> Tuple[Message, Attachment]:
        """Validate membership, stream upload to disk with size check & sha256, and persist DB records."""
        # 1. Authorize: verify uploader is an active member
        await PermissionService.get_active_membership(db, conversation_id, uploader_id)

        # 2. Idempotency check: if client_message_id is repeated, return existing message & attachment
        if client_message_id:
            existing_stmt = (
                select(Message)
                .options(selectinload(Message.sender), selectinload(Message.attachments))
                .where(
                    Message.conversation_id == conversation_id,
                    Message.sender_id == uploader_id,
                    Message.client_message_id == client_message_id,
                )
            )
            existing_msg = (await db.execute(existing_stmt)).scalar_one_or_none()
            if existing_msg and existing_msg.attachments:
                return existing_msg, existing_msg.attachments[0]

        # 3. Sanitize display filename
        original_filename = sanitize_filename(file.filename)

        # 4. Generate opaque storage key (never use client-supplied filename on disk)
        storage_key = f"{uuid.uuid4().hex}_{secrets.token_hex(8)}"
        target_path = (settings.UPLOAD_DIR / storage_key).resolve()
        temp_path = (settings.UPLOAD_DIR / f"{storage_key}.tmp").resolve()

        # Enforce storage directory boundary
        upload_dir_resolved = settings.UPLOAD_DIR.resolve()
        if not target_path.is_relative_to(upload_dir_resolved) or not temp_path.is_relative_to(upload_dir_resolved):
            raise BadRequestException("Invalid storage path target", code="INVALID_STORAGE_PATH")

        settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        hasher = hashlib.sha256()
        size_bytes = 0
        max_bytes = settings.MAX_UPLOAD_SIZE_BYTES

        # 5. Stream file in chunks, enforce size limit, compute SHA-256
        try:
            with open(temp_path, "wb") as f_out:
                while True:
                    chunk = await file.read(65536)  # 64 KB chunks
                    if not chunk:
                        break
                    size_bytes += len(chunk)
                    if size_bytes > max_bytes:
                        raise PayloadTooLargeException(
                            f"File size exceeds maximum allowed limit ({max_bytes // (1024 * 1024)} MB)",
                            code="FILE_TOO_LARGE",
                        )
                    hasher.update(chunk)
                    f_out.write(chunk)

            if size_bytes == 0:
                raise BadRequestException("Uploaded file cannot be empty", code="EMPTY_FILE")

            # Atomically rename temporary file to final storage key
            temp_path.replace(target_path)
        except Exception:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            if target_path.exists():
                target_path.unlink(missing_ok=True)
            raise

        # 6. Persist Message and Attachment entities
        try:
            now = utc_now()
            new_msg = Message(
                conversation_id=conversation_id,
                sender_id=uploader_id,
                client_message_id=client_message_id,
                message_type="file",
                content=original_filename,
                created_at=now,
            )
            db.add(new_msg)
            await db.flush()

            raw_mime = file.content_type or "application/octet-stream"
            mime_type = raw_mime[:100]

            new_att = Attachment(
                message_id=new_msg.id,
                original_filename=original_filename,
                storage_key=storage_key,
                mime_type=mime_type,
                size_bytes=size_bytes,
                sha256=hasher.hexdigest(),
                uploaded_by=uploader_id,
                created_at=now,
            )
            db.add(new_att)

            # Bump conversation updated_at
            conv_stmt = select(Conversation).where(Conversation.id == conversation_id)
            conv = (await db.execute(conv_stmt)).scalar_one_or_none()
            if conv:
                conv.updated_at = now

            await db.commit()

            # Reload full message with relationships
            stmt = (
                select(Message)
                .options(selectinload(Message.sender), selectinload(Message.attachments))
                .where(Message.id == new_msg.id)
            )
            loaded_msg = (await db.execute(stmt)).scalar_one()
            return loaded_msg, new_att

        except Exception:
            await db.rollback()
            if target_path.exists():
                target_path.unlink(missing_ok=True)
            raise

    @staticmethod
    async def get_attachment_for_download(
        db: AsyncSession,
        attachment_id: int,
        user_id: int,
    ) -> Tuple[Attachment, Path]:
        """Verify existence, check conversation membership, and return Attachment with safe file path."""
        stmt = (
            select(Attachment)
            .options(selectinload(Attachment.message))
            .where(Attachment.id == attachment_id)
        )
        att = (await db.execute(stmt)).scalar_one_or_none()
        if not att:
            raise NotFoundException("Attachment not found", code="ATTACHMENT_NOT_FOUND")

        if not att.message_id or not att.message:
            raise NotFoundException("Associated message not found", code="MESSAGE_NOT_FOUND")

        # Authorize: caller must be an active member of the conversation
        await PermissionService.get_active_membership(db, att.message.conversation_id, user_id)

        file_path = (settings.UPLOAD_DIR / att.storage_key).resolve()
        upload_dir_resolved = settings.UPLOAD_DIR.resolve()

        if not file_path.is_relative_to(upload_dir_resolved) or not file_path.is_file():
            raise NotFoundException("Attachment file not found on disk", code="FILE_NOT_FOUND")

        return att, file_path

    @staticmethod
    async def get_attachment_metadata(
        db: AsyncSession,
        attachment_id: int,
        user_id: int,
    ) -> Attachment:
        """Verify existence and membership, then return Attachment metadata."""
        stmt = (
            select(Attachment)
            .options(selectinload(Attachment.message))
            .where(Attachment.id == attachment_id)
        )
        att = (await db.execute(stmt)).scalar_one_or_none()
        if not att:
            raise NotFoundException("Attachment not found", code="ATTACHMENT_NOT_FOUND")

        if not att.message_id or not att.message:
            raise NotFoundException("Associated message not found", code="MESSAGE_NOT_FOUND")

        await PermissionService.get_active_membership(db, att.message.conversation_id, user_id)
        return att
