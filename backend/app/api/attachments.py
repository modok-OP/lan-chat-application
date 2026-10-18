"""Attachment download and metadata endpoints (Milestone 5)."""

from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.attachments import AttachmentResponse
from app.services.attachment_service import AttachmentService

router = APIRouter(prefix="/attachments", tags=["Attachments"])


@router.get(
    "/{attachment_id}/download",
    summary="Download Attachment",
    description="Authorize access via containing conversation membership and stream file with safe download headers.",
)
async def download_attachment(
    attachment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream authorized file attachment ensuring safe download headers and MIME protection."""
    att, file_path = await AttachmentService.get_attachment_for_download(
        db=db,
        attachment_id=attachment_id,
        user_id=current_user.id,
    )

    return FileResponse(
        path=str(file_path),
        filename=att.original_filename,
        media_type="application/octet-stream",
        headers={
            "X-Content-Type-Options": "nosniff",
            "ETag": f'"{att.sha256}"',
            "Cache-Control": "private, no-transform",
        },
    )


@router.get(
    "/{attachment_id}",
    response_model=AttachmentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Attachment Metadata",
    description="Retrieve metadata for an authorized file attachment.",
)
async def get_attachment_metadata(
    attachment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AttachmentResponse:
    """Return attachment metadata after verifying caller conversation membership."""
    att = await AttachmentService.get_attachment_metadata(
        db=db,
        attachment_id=attachment_id,
        user_id=current_user.id,
    )
    return AttachmentResponse.model_validate(att)
