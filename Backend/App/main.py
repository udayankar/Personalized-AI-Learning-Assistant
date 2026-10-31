from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .Routers import chat , documents , auth , signup
from .database import Base , engine
from . import models

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1234"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)

Base.metadata.create_all(bind=engine)

app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(auth.router)
app.include_router(signup.router)
