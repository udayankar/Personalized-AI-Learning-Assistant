from fastapi import APIRouter , status , Response , HTTPException , Depends 
from .. import schemas
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..oauth2 import create_access_token , get_current_user
from ..database import get_db
from ..utils import verify_password
from .. import models

router = APIRouter(prefix="/users")

@router.post("/login")
async def login(userinfo : schemas.Login_User , response : Response , db : Session = Depends(get_db)):
    user = db.execute(select(models.User).where(models.User.Email == userinfo.Email)).scalar_one_or_none()
    if user == None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND , detail="Wrong info")
    if not verify_password(userinfo.Password , user.Password):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND , detail="Incorect Password")
    token = create_access_token({"Email" : user.Email})
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=False,
        samesite="lax"
    )
    return {"message":"Login successful"}

@router.get("/me" , response_model=schemas.Return_Signup_User)
def me(current_user = Depends(get_current_user)):
    return current_user

@router.post("/logout")
async def logout(response : Response):
    response.delete_cookie("access_token")
    return {"message": "Logged out successfully"}