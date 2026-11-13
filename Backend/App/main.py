from fastapi import FastAPI
from .Routers import chat , documents , auth , signup
from .csrf import configure_csrf_protection

app = FastAPI()
configure_csrf_protection(app)

app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(auth.router)
app.include_router(signup.router)
