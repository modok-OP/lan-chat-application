from typing import Optional
from fastapi import APIRouter, Depends, Response, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    UserResponse,
    AuthStatusResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register New Account",
    description="Create a unique user account, hash the password with Argon2, and establish an initial session cookie.",
)
async def register(
    register_data: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    user, session_token = await AuthService.register_user(db, register_data)
    AuthService.set_session_cookie(response, session_token)
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Login",
    description="Authenticate user with username and password, then set an HttpOnly session cookie.",
)
async def login(
    login_data: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    user, session_token = await AuthService.authenticate_user(db, login_data)
    AuthService.set_session_cookie(response, session_token)
    return UserResponse.model_validate(user)


@router.post(
    "/logout",
    response_model=AuthStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Logout",
    description="Invalidate active session in the database and clear the session cookie.",
)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthStatusResponse:
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if token:
        await AuthService.invalidate_session(db, token)
    AuthService.clear_session_cookie(response)
    return AuthStatusResponse(message="Logged out successfully")


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Current User (Auth Alias)",
    description="Convenience alias for /api/me returning the currently authenticated user.",
)
async def get_current_user_profile(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    from app.api.deps import get_current_user
    user = await get_current_user(request, db)
    return UserResponse.model_validate(user)
