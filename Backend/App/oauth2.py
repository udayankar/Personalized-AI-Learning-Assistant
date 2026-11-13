import jwt
from jwt.exceptions import InvalidTokenError
from fastapi import status , Depends , HTTPException , Cookie , Request
from sqlalchemy.orm import Session
from datetime import datetime , UTC , timedelta
from . import models
from .database import get_db
from .csrf import SAFE_METHODS , validate_csrf_request
from dotenv import load_dotenv
import os

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))

def create_access_token(user_id: str):
    if not isinstance(user_id, str) or not user_id.isascii() or not user_id.isdecimal():
        raise ValueError("User ID must be a positive integer string")
    if int(user_id) <= 0 or str(int(user_id)) != user_id:
        raise ValueError("User ID must be a positive integer string")

    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire}
    token = jwt.encode(payload , SECRET_KEY , algorithm=ALGORITHM )
    return token

def verify_token(token : str , error):
    try:
        payload = jwt.decode(token , SECRET_KEY , algorithms=[ALGORITHM])
        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject.isascii() or not subject.isdecimal():
            raise error
        user_id = int(subject)
        if user_id <= 0 or str(user_id) != subject:
            raise error
        return user_id
    except InvalidTokenError:
        raise error
    except (TypeError, ValueError, OverflowError):
        raise error

def get_current_user(request : Request , access_token : str = Cookie(None) , db : Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if access_token is None:
        raise credentials_exception
    user_id = verify_token(access_token , credentials_exception)
    user = db.query(models.User).filter(models.User.ID == user_id).first()
    if user is None:
        raise credentials_exception
    if request.method.upper() not in SAFE_METHODS:
        validate_csrf_request(
            request,
            settings=getattr(request.app.state, "csrf_settings", None),
        )
    return user

def get_current_user_optional(request: Request , db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        user_id = verify_token(token, credentials_exception)
        return db.query(models.User).filter(models.User.ID == user_id).first()
    except Exception:
        return None
