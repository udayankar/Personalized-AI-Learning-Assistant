from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends
from starlette.concurrency import run_in_threadpool
from ..oauth2 import get_current_user
from Rag.ingest import Build_rag
from Rag.user_storage import Get_user_paths

router = APIRouter(prefix="/documents",tags=["Documents"])

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def Upload_Document(file: UploadFile = File(...), current_user = Depends(get_current_user)):
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="No file provided")
    if Path(file.filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST ,detail="Only PDF files are allowed")
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Invalid file type")
    filename = Path(file.filename.replace("\\", "/")).name
    if not filename or filename in {".", ".."}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    documents_dir, _ = Get_user_paths(current_user.ID)
    documents_dir.mkdir(parents=True, exist_ok=True)
    file_path = documents_dir / filename
    if file_path.resolve().parent != documents_dir.resolve():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    if file_path.exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,detail="A document with this filename already exists")
    try:
        with file_path.open("wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                buffer.write(chunk)
        await run_in_threadpool(Build_rag, current_user.ID)
    except HTTPException:
        if file_path.exists():
            file_path.unlink()
        raise
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
