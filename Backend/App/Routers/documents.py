from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, UploadFile, File, HTTPException, status
from starlette.concurrency import run_in_threadpool
from Rag.ingest import Build_rag

router = APIRouter(prefix="/documents",tags=["Documents"])

BASE_DIR = Path(__file__).resolve().parents[2]
DOCUMENTS_DIR = BASE_DIR / "Data" / "Documents"
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def Upload_Document(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="No file provided")
    if Path(file.filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST ,detail="Only PDF files are allowed")
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Invalid file type")
    filename = Path(file.filename).name
    file_path = DOCUMENTS_DIR / filename
    if file_path.exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,detail="A document with this filename already exists")
    try:
        with file_path.open("wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                buffer.write(chunk)
        await run_in_threadpool(Build_rag)
    except Exception:
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail="Failed to upload and process the document")
    finally:
        await file.close()

    return {
        "message": "Document uploaded and processed successfully",
        "filename": filename
    }