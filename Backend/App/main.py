from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool
from .config import get_upload_settings
from .csrf import configure_csrf_protection
from .document_recovery import recover_interrupted_document_work
from .rate_limit import validate_rate_limit_configuration
from Rag.relevance import Get_calibrated_relevance_threshold
from .Routers import chat, documents, auth, signup

@asynccontextmanager
async def lifespan(_app: FastAPI):
    await run_in_threadpool(Get_calibrated_relevance_threshold)
    await run_in_threadpool(recover_interrupted_document_work)
    yield

app = FastAPI(lifespan=lifespan)
configure_csrf_protection(app)
get_upload_settings()
validate_rate_limit_configuration()

app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(auth.router)
app.include_router(signup.router)
