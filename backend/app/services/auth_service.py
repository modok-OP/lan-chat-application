from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from fastapi import Response
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.errors import ConflictException, InvalidCredentialsException
from app.core.logging import logger
from app.core.security import (
    hash_password,
    verify_password,
    generate_session_token,
    hash_session_token,
)
from app.db.models import User, Session
from app.schemas.auth import RegisterRequest, LoginRequest


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class AuthService:
    """Business logic for user registration, authentication, and session management."""

    @staticmethod
    async def register_user(
        db: AsyncSession,
        register_data: RegisterRequest,
    ) -> Tuple[User, str]:
        """Register a new unique user, persist their account, and establish an initial session."""
        # Check for existing username (case-normalized)
        stmt = select(User).where(User.username == register_data.username)
        existing_user = (await db.execute(stmt)).scalar_one_or_none()
        if existing_user is not None:
            raise ConflictException(
                message=f"The username '{register_data.username}' is already taken.",
                code="USERNAME_ALREADY_EXISTS",
            )

        # Hash password using Argon2id
        hashed_password = hash_password(register_data.password)

        display_name = register_data.display_name or register_data.username

        new_user = User(
            username=register_data.username,
            display_name=display_name,
            password_hash=hashed_password,
            role="user",
            is_active=True,
            created_at=utc_now(),
            last_seen_at=utc_now(),
        )
        db.add(new_user)
        await db.flush()  # Generates new_user.id

        # Generate and store initial session
        raw_token = generate_session_token()
        token_hash = hash_session_token(raw_token)
        now = utc_now()
        expires_at = now + timedelta(seconds=settings.SESSION_MAX_AGE_SECONDS)

        session_record = Session(
            session_token_hash=token_hash,
            user_id=new_user.id,
            created_at=now,
            expires_at=expires_at,
            last_accessed_at=now,
        )
        db.add(session_record)
        await db.commit()
        await db.refresh(new_user)

        logger.info("New user registered: %s (id=%d)", new_user.username, new_user.id)
        return new_user, raw_token

    @staticmethod
    async def authenticate_user(
        db: AsyncSession,
        login_data: LoginRequest,
    ) -> Tuple[User, str]:
        """Verify user credentials and create a new session upon success."""
        stmt = select(User).where(User.username == login_data.username)
        user = (await db.execute(stmt)).scalar_one_or_none()

        # Guard against non-existent user or inactive account
        if user is None or not user.is_active:
            logger.warning("Failed login attempt for username: %s", login_data.username)
            raise InvalidCredentialsException()

        # Verify password hash
        if not verify_password(login_data.password, user.password_hash):
            logger.warning("Invalid password for username: %s", login_data.username)
            raise InvalidCredentialsException()

        # Update last seen timestamp
        user.last_seen_at = utc_now()

        # Generate session
        raw_token = generate_session_token()
        token_hash = hash_session_token(raw_token)
        now = utc_now()
        expires_at = now + timedelta(seconds=settings.SESSION_MAX_AGE_SECONDS)

        session_record = Session(
            session_token_hash=token_hash,
            user_id=user.id,
            created_at=now,
            expires_at=expires_at,
            last_accessed_at=now,
        )
        db.add(session_record)
        await db.commit()
        await db.refresh(user)

        logger.info("User authenticated: %s (id=%d)", user.username, user.id)
        return user, raw_token

    @staticmethod
    async def get_user_by_session_token(
        db: AsyncSession,
        raw_token: str,
    ) -> Optional[User]:
        """Look up active session and user by raw opaque session token."""
        if not raw_token:
            return None

        token_hash = hash_session_token(raw_token)
        now = utc_now()

        stmt = (
            select(Session)
            .options(selectinload(Session.user))
            .where(
                Session.session_token_hash == token_hash,
                Session.expires_at > now,
            )
        )
        session_record = (await db.execute(stmt)).scalar_one_or_none()

        if session_record is None or not session_record.user or not session_record.user.is_active:
            return None

        # Refresh last accessed and seen timestamps
        session_record.last_accessed_at = now
        session_record.user.last_seen_at = now
        await db.commit()

        return session_record.user

    @staticmethod
    async def invalidate_session(
        db: AsyncSession,
        raw_token: str,
    ) -> bool:
        """Invalidate an active session on logout."""
        if not raw_token:
            return False

        token_hash = hash_session_token(raw_token)
        stmt = delete(Session).where(Session.session_token_hash == token_hash)
        result = await db.execute(stmt)
        await db.commit()

        return result.rowcount > 0

    @staticmethod
    def set_session_cookie(response: Response, raw_token: str) -> None:
        """Attach session cookie with HttpOnly and Lax SameSite flags."""
        response.set_cookie(
            key=settings.SESSION_COOKIE_NAME,
            value=raw_token,
            max_age=settings.SESSION_MAX_AGE_SECONDS,
            httponly=True,
            samesite=settings.SESSION_COOKIE_SAMESITE,
            secure=settings.SESSION_COOKIE_SECURE,
            path="/",
        )

    @staticmethod
    def clear_session_cookie(response: Response) -> None:
        """Clear the session cookie upon logout."""
        response.delete_cookie(
            key=settings.SESSION_COOKIE_NAME,
            path="/",
            httponly=True,
            samesite=settings.SESSION_COOKIE_SAMESITE,
            secure=settings.SESSION_COOKIE_SECURE,
        )
