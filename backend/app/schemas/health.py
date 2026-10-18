from datetime import datetime, timezone
from typing import List
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check diagnostic response payload."""

    status: str = Field(..., description="Overall service status (e.g., healthy)")
    app_name: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")
    database: str = Field(..., description="Database connectivity status (connected/disconnected)")
    environment: str = Field(..., description="Current running environment")
    lan_ips: List[str] = Field(default_factory=list, description="Discovered reachable LAN IPv4 addresses")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Current server UTC timestamp",
    )
