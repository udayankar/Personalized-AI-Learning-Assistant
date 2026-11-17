import hashlib
import tempfile
import uuid
from contextlib import suppress
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import models, schemas
from ..config import get_upload_settings
from ..database import get_db
from ..oauth2 import get_current_user
from ..upload_storage import (
    InvalidPdf, PdfPageLimitExceeded, UploadTooLarge, UserStorageQuotaExceeded,
    per_user_upload_lock, sanitized_display_filename, validate_pdf, write_staged_upload,
)
from ..rate_limit import user_rate_limit
from Rag.ingest import Process_document
from Rag.vector_store import Insert_document_chunks

router = APIRouter(prefix="/documents", tags=["Documents"])


def _http_error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _document_response(document: models.Document, user_id: int) -> dict:
    return {
        "id": document.id, "filename": document.filename,
        "uploaded_at": document.uploaded_at, "updated_at": document.updated_at,
        "file_size_bytes": document.file_size_bytes, "page_count": document.page_count,
        "status": document.status, "available": document.status == "READY",
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@router.post("/upload", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(user_rate_limit("upload"))])
async def Upload_Document(file: UploadFile = File(...), current_user=Depends(get_current_user),
                          db: Session = Depends(get_db)):
    staged_path = None
    document = None
    try:
        if not file.filename:
            raise _http_error(400, "No file provided")
        normalized = file.filename.replace("\\", "/").rsplit("/", 1)[-1]
        if Path(normalized).suffix.lower() != ".pdf" or file.content_type != "application/pdf":
            raise _http_error(415, "Only PDF files are allowed")
        settings = get_upload_settings()
        display_name = sanitized_display_filename(file.filename)
        lock_path = Path(tempfile.gettempdir()) / "learning-assistant-locks" / f"user-{current_user.ID}.lock"
        async with per_user_upload_lock(lock_path):
            duplicate = db.scalar(select(models.Document.id).where(
                models.Document.user_id == current_user.ID,
                models.Document.filename == display_name,
                models.Document.status.in_(("PROCESSING", "READY")),
            ).limit(1))
            if duplicate:
                raise _http_error(409, "A document with this filename already exists")
            used = db.scalar(select(func.coalesce(func.sum(models.Document.file_size_bytes), 0)).where(
                models.Document.user_id == current_user.ID,
                models.Document.status.in_(("PROCESSING", "READY")),
            )) or 0
            remaining = settings.max_user_pdf_storage_bytes - used
            if remaining <= 0:
                raise _http_error(413, "Your stored PDF size limit has been reached")
            temp_root = Path(tempfile.gettempdir()) / "learning-assistant-uploads"
            temp_root.mkdir(parents=True, exist_ok=True)
            fd = tempfile.NamedTemporaryFile(prefix="upload-", suffix=".pdf", dir=temp_root, delete=False)
            staged_path = Path(fd.name)
            fd.close()
            staged_path.unlink(missing_ok=True)
            try:
                size = await write_staged_upload(file, staged_path, settings.max_pdf_upload_size_bytes, remaining)
            except UploadTooLarge:
                raise _http_error(413, "The PDF exceeds the per-file size limit")
            except UserStorageQuotaExceeded:
                raise _http_error(413, "The PDF would exceed your stored PDF size limit")
            except InvalidPdf:
                raise _http_error(400, "The uploaded PDF is empty or invalid")
            page_count = await run_in_threadpool(validate_pdf, staged_path, settings.max_pdf_page_count)
            document = models.Document(
                user_id=current_user.ID, filename=display_name,
                storage_filename=f"temporary-{uuid.uuid4().hex}", file_size_bytes=size,
                page_count=page_count, sha256=await run_in_threadpool(_sha256, staged_path),
                status="PROCESSING",
            )
            db.add(document)
            db.commit()
            db.refresh(document)
            chunks, embeddings = await run_in_threadpool(Process_document, staged_path)
            Insert_document_chunks(db, document, chunks, embeddings)
            document.status = "READY"
            db.commit()
        return {"message": "Document uploaded and processed successfully", "filename": display_name}
    except HTTPException:
        if document is not None:
            with suppress(Exception):
                db.rollback()
                document.status = "FAILED"
                db.commit()
        raise
    except PdfPageLimitExceeded:
        raise _http_error(413, "The PDF exceeds the page limit")
    except InvalidPdf:
        raise _http_error(400, "The PDF is unreadable, encrypted, or contains no extractable text")
    except Exception as error:
        if document is not None:
            with suppress(Exception):
                db.rollback()
                document.status = "FAILED"
                db.commit()
        raise _http_error(500, "Failed to process the uploaded PDF") from error
    finally:
        if staged_path is not None:
            with suppress(OSError):
                staged_path.unlink(missing_ok=True)
        with suppress(Exception):
            await file.close()


@router.get("", response_model=schemas.DocumentList)
def List_Documents(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(models.Document).where(
        models.Document.user_id == current_user.ID
    ).order_by(models.Document.uploaded_at.desc(), models.Document.id)).all()
    return {"documents": [_document_response(row, current_user.ID) for row in rows]}


@router.get("/{document_id}", response_model=schemas.DocumentDetails)
def Get_Document(document_id: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(models.Document).where(
        models.Document.id == document_id, models.Document.user_id == current_user.ID
    ))
    if row is None:
        raise _http_error(404, "Document not found")
    return _document_response(row, current_user.ID)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def Delete_Document(document_id: str, current_user=Depends(get_current_user),
                          db: Session = Depends(get_db)):
    user_id = current_user.ID
    lock_path = Path(tempfile.gettempdir()) / "learning-assistant-locks" / f"user-{user_id}.lock"
    async with per_user_upload_lock(lock_path):
        row = db.scalar(select(models.Document).where(
            models.Document.id == document_id, models.Document.user_id == user_id
        ))
        if row is None:
            raise _http_error(404, "Document not found")
        if row.status == "PROCESSING":
            raise _http_error(409, "Document processing is still in progress")
        if row.status != "DELETING":
            row.status = "DELETING"
            db.execute(delete(models.AnswerCache).where(models.AnswerCache.user_id == user_id))
            db.commit()
        try:
            db.delete(row)  # chunks cascade; no embedding API call or filesystem index rebuild
            db.execute(delete(models.AnswerCache).where(models.AnswerCache.user_id == user_id))
            db.commit()
        except Exception as error:
            db.rollback()
            raise _http_error(503, "Document deletion is incomplete and can be retried") from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
