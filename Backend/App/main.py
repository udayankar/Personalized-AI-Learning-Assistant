from fastapi import FastAPI
from .Routers import chat , documents , auth

app = FastAPI()
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(auth.router)

