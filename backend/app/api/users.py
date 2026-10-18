from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import UserResponse

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "",
    response_model=List[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="Search Eligible Users",
    description="Search active users to start a direct chat or invite to a group.",
)
async def search_users(
    search: Optional[str] = Query(None, description="Search by username or display name"),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[UserResponse]:
    query = select(User).where(User.is_active == True, User.id != current_user.id)

    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        query = query.where(
            or_(
                User.username.ilike(term),
                User.display_name.ilike(term),
            )
        )

    query = query.order_by(User.username.asc()).limit(limit)
    users = (await db.execute(query)).scalars().all()

    return [UserResponse.model_validate(u) for u in users]


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Current User Profile",
    description="Return the profile of the currently authenticated user based on the session cookie.",
)
async def get_my_profile(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)
