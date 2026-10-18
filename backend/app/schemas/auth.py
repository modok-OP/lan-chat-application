import re
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict


USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_]+$")


class RegisterRequest(BaseModel):
    """User registration payload."""

    username: str = Field(
        ...,
        min_length=3,
        max_length=30,
        description="Unique username consisting of alphanumeric characters and underscores",
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Plaintext password (minimum 8 characters)",
    )
    display_name: Optional[str] = Field(
        None,
        max_length=50,
        description="Display name shown in conversations. Defaults to username if omitted.",
    )

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        clean = v.strip().lower()
        if not USERNAME_REGEX.match(clean):
            raise ValueError("Username can only contain alphanumeric characters and underscores.")
        return clean

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip()
            if clean:
                return clean
        return None


class LoginRequest(BaseModel):
    """User authentication payload."""

    username: str = Field(..., min_length=1, max_length=50, description="Username")
    password: str = Field(..., min_length=1, max_length=128, description="Password")

    @field_validator("username")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        return v.strip().lower()


class UserResponse(BaseModel):
    """User profile data exposed to client."""

    id: int
    username: str
    display_name: str
    role: str
    is_active: bool
    created_at: datetime
    last_seen_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AuthStatusResponse(BaseModel):
    """Simple status message response."""

    message: str
