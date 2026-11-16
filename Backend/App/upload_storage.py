import asyncio
import os
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import unquote

from pypdf import PdfReader


STREAM_CHUNK_SIZE = 64 * 1024


class UploadTooLarge(Exception):
    pass


class UserStorageQuotaExceeded(Exception):
    pass


class PdfPageLimitExceeded(Exception):
    pass


class InvalidPdf(Exception):
    pass


def sanitized_display_filename(filename: str) -> str:
    # Treat both slash styles as separators, then retain only a short safe display name.
    basename = unquote(filename).replace("\\", "/").rsplit("/", 1)[-1]
    stem = Path(basename).stem
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", stem)
    stem = re.sub(r"\s+", "_", stem).strip(" ._-_")[:100]
    return f"{stem or 'document'}.pdf"


def generated_storage_filename(display_filename: str) -> str:
    stem = Path(display_filename).stem
    return f"{stem}--{uuid.uuid4().hex}.pdf"


def has_duplicate_display_name(documents_dir: Path, display_filename: str) -> bool:
    display_stem = Path(display_filename).stem
    for existing_path in documents_dir.iterdir():
        if not existing_path.is_file() or existing_path.suffix.lower() != ".pdf":
            continue
        existing_stem = existing_path.stem
        if existing_stem == display_stem or existing_stem.startswith(f"{display_stem}--"):
            return True
    return False


def stored_pdf_size_bytes(documents_dir: Path) -> int:
    return sum(
        path.stat().st_size
        for path in documents_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".pdf"
    )


async def write_staged_upload(upload, staged_path: Path, file_limit: int, quota_remaining: int) -> int:
    size = 0
    with staged_path.open("xb") as destination:
        while chunk := await upload.read(STREAM_CHUNK_SIZE):
            size += len(chunk)
            if size > file_limit:
                raise UploadTooLarge
            if size > quota_remaining:
                raise UserStorageQuotaExceeded
            destination.write(chunk)
        destination.flush()
        os.fsync(destination.fileno())

    if size == 0:
        raise InvalidPdf
    return size


def validate_pdf(path: Path, page_limit: int) -> int:
    try:
        with path.open("rb") as staged_file:
            header = staged_file.read(1024)
        if b"%PDF-" not in header:
            raise InvalidPdf

        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise InvalidPdf
        page_count = len(reader.pages)
        if page_count == 0:
            raise InvalidPdf
        if page_count > page_limit:
            raise PdfPageLimitExceeded
        if not any((page.extract_text() or "").strip() for page in reader.pages):
            raise InvalidPdf
        return page_count
    except (InvalidPdf, PdfPageLimitExceeded):
        raise
    except Exception as error:
        raise InvalidPdf from error


def _try_acquire_file_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise BlockingIOError from error
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise
        return handle
    except Exception:
        handle.close()
        raise


def _release_file_lock(handle) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


@asynccontextmanager
async def per_user_upload_lock(lock_path: Path):
    # Nonblocking OS locks coordinate same-user upload and delete operations
    # across application workers, including their FAISS index rebuilds.
    while True:
        try:
            handle = _try_acquire_file_lock(lock_path)
            break
        except BlockingIOError:
            await asyncio.sleep(0.05)
    try:
        yield
    finally:
        _release_file_lock(handle)
