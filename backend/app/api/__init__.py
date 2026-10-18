from fastapi import APIRouter, Depends
from app.api.health import router as health_router
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.conversations import router as conversations_router
from app.api.messages import router as messages_router
from app.api.attachments import router as attachments_router
from app.api.websocket import router as websocket_router
from app.api.deps import get_current_user
from app.db.models import User
from app.schemas.auth import UserResponse

api_router = APIRouter()

# Core diagnostic and current user
api_router.include_router(health_router)


@api_router.get(
    "/me",
    response_model=UserResponse,
    tags=["Authentication"],
    summary="Get Current User",
    description="Return the profile of the currently authenticated user.",
)
async def get_current_authenticated_user(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    return UserResponse.model_validate(current_user)


# Feature routers
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(conversations_router)
api_router.include_router(messages_router)
api_router.include_router(attachments_router)
api_router.include_router(websocket_router)
