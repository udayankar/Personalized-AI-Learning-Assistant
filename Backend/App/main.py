from fastapi import FastAPI
from .config import get_upload_settings
from .csrf import configure_csrf_protection
from .document_recovery import recover_interrupted_document_work

app = FastAPI()
app.add_event_handler("startup", recover_interrupted_document_work)
# Validate all runtime security settings before routers initialize provider clients.
configure_csrf_protection(app)
get_upload_settings()

from .Routers import chat, documents, auth, signup

app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(auth.router)
app.include_router(signup.router)
