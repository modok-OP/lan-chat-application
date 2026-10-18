from fastapi import APIRouter, status
from app.core.config import settings
from app.core.network import get_lan_ips
from app.db.session import check_database_health
from app.schemas.health import HealthResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Application Health Diagnostics",
    description="Check the server operational status, database connectivity, and environment.",
)
async def get_health() -> HealthResponse:
    db_connected = await check_database_health()
    return HealthResponse(
        status="healthy" if db_connected else "degraded",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        database="connected" if db_connected else "disconnected",
        environment=settings.APP_ENV,
        lan_ips=get_lan_ips(),
    )
