import os
import uuid
from contextlib import suppress
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import models, schemas
from ..config import get_upload_settings
from ..database import get_db
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
from Rag.document_tracker import Calculate_file_hash
from Rag.user_storage import Get_user_paths


router = APIRouter(prefix="/documents", tags=["Documents"])


def _remove_file(path: Path | None) -> None:
    if path is None:
        return
    with suppress(OSError):
        path.unlink(missing_ok=True)


def _http_error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _document_file_path(user_id: int, storage_filename: str) -> Path:
    if Path(storage_filename).name != storage_filename or "/" in storage_filename or "\\" in storage_filename:
        raise ValueError("Invalid stored document name")
    documents_dir, _ = Get_user_paths(user_id)
    resolved_dir = documents_dir.resolve()
    expected_dir = documents_dir.parent.resolve() / documents_dir.name
    if resolved_dir != expected_dir:
        raise ValueError("User document directory is outside its configured root")
    path = documents_dir / storage_filename
    if path.resolve().parent != resolved_dir:
        raise ValueError("Stored document is outside the user's directory")
    return path


def _document_response(document: models.Document, user_id: int) -> dict:
    try:
        available = _document_file_path(user_id, document.storage_filename).is_file()
    except (OSError, ValueError):
        available = False
    return {
        "id": document.id,
        "filename": document.filename,
        "uploaded_at": document.uploaded_at,
        "updated_at": document.updated_at,
        "file_size_bytes": document.file_size_bytes,
        "page_count": document.page_count,
        "status": document.status,
        "available": available,
    }


def _indexed_document_hashes(db: Session, user_id: int) -> dict[str, str]:
    """Return catalog PDF hashes eligible for inclusion in the user's index."""
    rows = db.execute(
        select(models.Document.storage_filename, models.Document.sha256).where(
            models.Document.user_id == user_id,
            models.Document.status.in_(("PROCESSING", "READY")),
        )
    ).all()
    return {filename: digest for filename, digest in rows}


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def Upload_Document(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    staged_path: Path | None = None
    published_path: Path | None = None
    document_record: models.Document | None = None
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
                staged_size = await write_staged_upload(
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
                page_count = await run_in_threadpool(
                    validate_pdf, staged_path, settings.max_pdf_page_count
                )
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

            document_record = models.Document(
                user_id=current_user.ID,
                filename=display_filename,
                storage_filename=storage_filename,
                file_size_bytes=staged_size,
                page_count=page_count,
                sha256=await run_in_threadpool(Calculate_file_hash, published_path),
                status="PROCESSING",
            )
            db.add(document_record)
            db.commit()
            db.refresh(document_record)

            # Keep the existing per-user file lock through index rebuilding so
            # another upload or delete cannot rebuild the same user's index at once.
            catalog_hashes = _indexed_document_hashes(db, current_user.ID)
            await run_in_threadpool(
                Build_rag,
                current_user.ID,
                eligible_storage_filenames=set(catalog_hashes),
                document_hashes=catalog_hashes,
                lock_held=True,
            )
            document_record.status = "READY"
            db.commit()
        published_path = None
        return {
            "message": "Document uploaded and processed successfully",
            "filename": display_filename,
        }
    except HTTPException:
        _remove_file(published_path)
        if document_record is not None:
            with suppress(Exception):
                db.rollback()
                document_record.status = "FAILED"
                db.commit()
        raise
    except Exception:
        _remove_file(published_path)
        if document_record is not None:
            with suppress(Exception):
                db.rollback()
                document_record.status = "FAILED"
                db.commit()
        raise _http_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Failed to process the uploaded PDF",
        )
    finally:
        _remove_file(staged_path)
        with suppress(Exception):
            await file.close()


@router.get("", response_model=schemas.DocumentList)
def List_Documents(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    documents = db.scalars(
        select(models.Document)
        .where(models.Document.user_id == current_user.ID)
        .order_by(models.Document.uploaded_at.desc(), models.Document.id)
    ).all()
    return {"documents": [_document_response(item, current_user.ID) for item in documents]}


@router.get("/{document_id}", response_model=schemas.DocumentDetails)
def Get_Document(
    document_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = db.scalar(select(models.Document).where(
        models.Document.id == document_id,
        models.Document.user_id == current_user.ID,
    ))
    if document is None:
        raise _http_error(status.HTTP_404_NOT_FOUND, "Document not found")
    return _document_response(document, current_user.ID)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def Delete_Document(
    document_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current_user.ID
    documents_dir, _ = Get_user_paths(user_id)
    documents_dir.mkdir(parents=True, exist_ok=True)
    resolved_documents_dir = documents_dir.resolve()
    expected_user_dir = documents_dir.parent.resolve() / documents_dir.name
    if resolved_documents_dir != expected_user_dir:
        raise _http_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "Upload storage is unavailable")
    lock_path = resolved_documents_dir / ".upload.lock"
    tombstone_path = resolved_documents_dir / f".deleting-{document_id}.part"

    async with per_user_upload_lock(lock_path):
        document = db.scalar(select(models.Document).where(
            models.Document.id == document_id,
            models.Document.user_id == user_id,
        ))
        if document is None:
            raise _http_error(status.HTTP_404_NOT_FOUND, "Document not found")
        if document.status == "PROCESSING":
            raise _http_error(status.HTTP_409_CONFLICT, "Document processing is still in progress")

        source_path = _document_file_path(user_id, document.storage_filename)
        if document.status != "DELETING":
            document.status = "DELETING"
            db.execute(delete(models.AnswerCache).where(models.AnswerCache.user_id == user_id))
            db.commit()

        try:
            if source_path.exists() and not tombstone_path.exists():
                os.replace(source_path, tombstone_path)
            catalog_hashes = _indexed_document_hashes(db, user_id)
            await run_in_threadpool(
                Build_rag,
                user_id,
                eligible_storage_filenames=set(catalog_hashes),
                document_hashes=catalog_hashes,
                lock_held=True,
            )
        except Exception:
            with suppress(Exception):
                db.rollback()
                document.status = "DELETING"
                db.commit()
            raise _http_error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Document deletion is incomplete and can be retried",
            )

        try:
            tombstone_path.unlink(missing_ok=True)
            db.delete(document)
            db.commit()
        except Exception:
            with suppress(Exception):
                db.rollback()
                document.status = "DELETING"
                db.commit()
            raise _http_error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Document deletion is incomplete and can be retried",
            )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
