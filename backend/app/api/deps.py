from typing import Optional
from fastapi import Cookie, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import UnauthorizedException
from app.db.models import User
from app.db.session import get_db
from app.services.auth_service import AuthService


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    lan_chat_session: Optional[str] = Cookie(None, alias=settings.SESSION_COOKIE_NAME),
) -> User:
    """Dependency that verifies the session cookie and returns the active User."""
    token = lan_chat_session

    # If cookie is not populated by parameter name alias, check directly in request.cookies
    if not token and settings.SESSION_COOKIE_NAME in request.cookies:
        token = request.cookies.get(settings.SESSION_COOKIE_NAME)

    if not token:
        raise UnauthorizedException("Authentication required")

    user = await AuthService.get_user_by_session_token(db, token)
    if user is None:
        raise UnauthorizedException("Invalid or expired session")

    return user


async def get_optional_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    lan_chat_session: Optional[str] = Cookie(None, alias=settings.SESSION_COOKIE_NAME),
) -> Optional[User]:
    """Dependency that returns User if valid session exists, otherwise None."""
    token = lan_chat_session or request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        return None

    return await AuthService.get_user_by_session_token(db, token)
