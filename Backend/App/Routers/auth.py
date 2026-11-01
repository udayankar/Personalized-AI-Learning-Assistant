from fastapi import APIRouter , status , Response , HTTPException , Depends, Request
from .. import schemas
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..oauth2 import create_access_token , get_current_user
from ..config import get_security_settings
from ..csrf import (CSRF_COOKIE_NAME , PREAUTH_COOKIE_NAME , issue_csrf_token ,require_csrf , token_is_valid,)
import secrets
from ..database import get_db
from ..utils import verify_password
from .. import models

router = APIRouter(prefix="/users")

@router.post("/login")
async def login(userinfo : schemas.Login_User , response : Response , request: Request, db : Session = Depends(get_db), _csrf=Depends(require_csrf)):
    user = db.execute(select(models.User).where(models.User.Email == userinfo.Email)).scalar_one_or_none()
    if user == None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND , detail="Wrong info")
    if not verify_password(userinfo.Password , user.Password):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND , detail="Incorect Password")
    token = create_access_token({"Email" : user.Email})
    settings = getattr(request.app.state, "csrf_settings", None) or get_security_settings()
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        path=settings.cookie_path,
    )
    csrf_token = issue_csrf_token(response, access_token=token, settings=settings)
    response.delete_cookie(
        PREAUTH_COOKIE_NAME, path=settings.cookie_path, domain=settings.cookie_domain,
        secure=settings.cookie_secure, httponly=True, samesite=settings.cookie_samesite,
    )
    response.headers["Cache-Control"] = "no-store"
    return {"message":"Login successful", "csrf_token": csrf_token}

@router.get("/csrf")
def get_csrf_token(request: Request, response: Response):
    settings = getattr(request.app.state, "csrf_settings", None) or get_security_settings()
    access_token = request.cookies.get("access_token")
    preauth_session = request.cookies.get(PREAUTH_COOKIE_NAME)
    if not access_token and not preauth_session:
        preauth_session = secrets.token_urlsafe(32)
        response.set_cookie(
            PREAUTH_COOKIE_NAME, preauth_session, max_age=settings.csrf_token_ttl_seconds,
            httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite,
            domain=settings.cookie_domain, path=settings.cookie_path,
        )
    current = request.cookies.get(CSRF_COOKIE_NAME)
    if token_is_valid(current, request, settings):
        token = current
    else:
        token = issue_csrf_token(
            response, access_token=access_token, settings=settings,
            preauth_session=preauth_session,
        )
    response.headers["Cache-Control"] = "no-store"
    return {"csrf_token": token}

@router.get("/me" , response_model=schemas.Return_Signup_User)
def me(current_user = Depends(get_current_user)):
    return current_user

@router.post("/logout")
async def logout(request: Request, response : Response, _csrf=Depends(require_csrf)):
    settings = getattr(request.app.state, "csrf_settings", None) or get_security_settings()
    response.delete_cookie(
        "access_token",
        path=settings.cookie_path,
        domain=settings.cookie_domain,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )
    response.delete_cookie(
        CSRF_COOKIE_NAME,
        path=settings.cookie_path,
        domain=settings.cookie_domain,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )
    response.delete_cookie(
        PREAUTH_COOKIE_NAME,
        path=settings.cookie_path,
        domain=settings.cookie_domain,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )
    return {"message": "Logged out successfully"}
