import os
import uuid
from contextlib import suppress
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from starlette.concurrency import run_in_threadpool

from ..config import get_upload_settings
from ..oauth2 import get_current_user
from ..upload_storage import (
    InvalidPdf,
    PdfPageLimitExceeded,
    UploadTooLarge,
    UserStorageQuotaExceeded,
    generated_storage_filename,
    has_duplicate_display_name,
    per_user_upload_lock,
    sanitized_display_filename,
    stored_pdf_size_bytes,
    validate_pdf,
    write_staged_upload,
)
from Rag.ingest import Build_rag
from Rag.user_storage import Get_user_paths


router = APIRouter(prefix="/documents", tags=["Documents"])


def _remove_file(path: Path | None) -> None:
    if path is None:
        return
    with suppress(OSError):
        path.unlink(missing_ok=True)


def _http_error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def Upload_Document(file: UploadFile = File(...), current_user=Depends(get_current_user)):
    staged_path: Path | None = None
    published_path: Path | None = None
    try:
        if not file.filename:
            raise _http_error(status.HTTP_400_BAD_REQUEST, "No file provided")

        normalized_input = file.filename.replace("\\", "/").rsplit("/", 1)[-1]
        if Path(normalized_input).suffix.lower() != ".pdf":
            raise _http_error(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only PDF files are allowed")
        if file.content_type != "application/pdf":
            raise _http_error(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Invalid file type")

        settings = get_upload_settings()
        display_filename = sanitized_display_filename(file.filename)
        documents_dir, _ = Get_user_paths(current_user.ID)
        try:
            documents_dir.mkdir(parents=True, exist_ok=True)
            resolved_documents_dir = documents_dir.resolve()
            expected_user_dir = documents_dir.parent.resolve() / documents_dir.name
            if resolved_documents_dir != expected_user_dir:
                raise OSError("User document directory is outside its configured root")
        except OSError:
            raise _http_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "Upload storage is unavailable")

        lock_path = resolved_documents_dir / ".upload.lock"
        async with per_user_upload_lock(lock_path):
            if has_duplicate_display_name(resolved_documents_dir, display_filename):
                raise _http_error(
                    status.HTTP_409_CONFLICT,
                    "A document with this filename already exists",
                )

            try:
                used_bytes = stored_pdf_size_bytes(resolved_documents_dir)
            except OSError:
                raise _http_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "Upload storage is unavailable")
            quota_remaining = settings.max_user_pdf_storage_bytes - used_bytes
            if quota_remaining <= 0:
                raise _http_error(
                    status.HTTP_413_CONTENT_TOO_LARGE,
                    "Your stored PDF size limit has been reached",
                )

            staged_path = resolved_documents_dir / f".upload-{uuid.uuid4().hex}.part"
            try:
                await write_staged_upload(
                    file,
                    staged_path,
                    settings.max_pdf_upload_size_bytes,
                    quota_remaining,
                )
            except UploadTooLarge:
                raise _http_error(
                    status.HTTP_413_CONTENT_TOO_LARGE,
                    "The PDF exceeds the per-file size limit",
                )
            except UserStorageQuotaExceeded:
                raise _http_error(
                    status.HTTP_413_CONTENT_TOO_LARGE,
                    "The PDF would exceed your stored PDF size limit",
                )
            except InvalidPdf:
                raise _http_error(status.HTTP_400_BAD_REQUEST, "The uploaded PDF is empty or invalid")
            except OSError:
                raise _http_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "Temporary upload storage is unavailable")

            try:
                await run_in_threadpool(validate_pdf, staged_path, settings.max_pdf_page_count)
            except PdfPageLimitExceeded:
                raise _http_error(
                    status.HTTP_413_CONTENT_TOO_LARGE,
                    "The PDF exceeds the page limit",
                )
            except InvalidPdf:
                raise _http_error(
                    status.HTTP_400_BAD_REQUEST,
                    "The PDF is unreadable, encrypted, or contains no extractable text",
                )

            storage_filename = generated_storage_filename(display_filename)
            published_path = resolved_documents_dir / storage_filename
            if published_path.resolve().parent != resolved_documents_dir:
                raise _http_error(status.HTTP_400_BAD_REQUEST, "Invalid filename")
            try:
                os.replace(staged_path, published_path)
                staged_path = None
            except OSError:
                published_path = None
                raise _http_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "Unable to store the uploaded PDF")

        # The upload/quota lock is released before ingestion. T0-05 will handle
        # same-user FAISS write serialization and atomic index publication.
        await run_in_threadpool(Build_rag, current_user.ID)
        published_path = None
        return {
            "message": "Document uploaded and processed successfully",
            "filename": display_filename,
        }
    except HTTPException:
        _remove_file(published_path)
        raise
    except Exception:
        _remove_file(published_path)
        raise _http_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Failed to process the uploaded PDF",
        )
    finally:
        _remove_file(staged_path)
        with suppress(Exception):
            await file.close()
