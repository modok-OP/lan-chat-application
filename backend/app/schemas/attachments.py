from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, computed_field


class AttachmentResponse(BaseModel):
    """File attachment public representation."""

    id: int
    message_id: Optional[int] = None
    original_filename: str
    mime_type: str = "application/octet-stream"
    size_bytes: int
    sha256: str
    uploaded_by: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def download_url(self) -> str:
        """Safe relative download URL for authorized clients."""
        return f"/api/attachments/{self.id}/download"
