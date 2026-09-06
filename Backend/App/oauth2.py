import jwt
from jwt.exceptions import InvalidTokenError
from fastapi import status , Depends , HTTPException , Cookie , Request
from sqlalchemy.orm import Session
from datetime import datetime , UTC , timedelta
from App import models
from .database import get_db
from dotenv import load_dotenv
import os

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))

def create_access_token(data : dict):
    payload = data.copy()
    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload.update({"exp" :  expire})
    token = jwt.encode(payload , SECRET_KEY , algorithm=ALGORITHM )
    return token

def verify_token(token : str , error):
    try:
        payload = jwt.decode(token , SECRET_KEY , algorithms=[ALGORITHM])
        email = payload.get("Email")
        if email == None:
            raise error
        return email
    except InvalidTokenError:
        raise error

def get_current_user(access_token: str = Cookie(None) , db : Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if access_token is None:
        raise credentials_exception
    email = verify_token(access_token , credentials_exception)
    user = db.query(models.User).filter(models.User.Email == email).first()
    if user is None:
        raise credentials_exception
    return user

def get_current_user_optional(request: Request , db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("Email")
        if not email:
            return None
        return db.query(models.User).filter(models.User.Email == email).first()
    except Exception:
        return None