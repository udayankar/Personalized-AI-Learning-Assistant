from fastapi import FastAPI
from .Routers import chat , documents , auth , signup
from .database import Base , engine
from . import models
from .csrf import configure_csrf_protection

app = FastAPI()
configure_csrf_protection(app)

Base.metadata.create_all(bind=engine)

app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(auth.router)
app.include_router(signup.router)
