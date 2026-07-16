from datetime import datetime

from pydantic import BaseModel

from app.models.document import DocumentStatus


# ── Request ────────────────────────────────────────────────────────────


# ── Response ──────────────────────────────────────────────────────────


class DocumentResponse(BaseModel):
    id: int
    filename: str
    original_filename: str
    file_size: int
    mime_type: str
    status: DocumentStatus
    progress: int
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UploadResponse(BaseModel):
    id: int
    filename: str
    status: DocumentStatus
    message: str


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int


class DeleteResponse(BaseModel):
    message: str


class ReprocessResponse(BaseModel):
    id: int
    filename: str
    status: DocumentStatus
    message: str


# ── Storage ────────────────────────────────────────────────────────────


class StorageUsageResponse(BaseModel):
    total_used_bytes: int
    quota_bytes: int
    used_percent: float

    model_config = {"from_attributes": True}


# ── WebSocket payload ──────────────────────────────────────────────────


class ProgressPayload(BaseModel):
    status: DocumentStatus
    progress: int
    message: str = ""
