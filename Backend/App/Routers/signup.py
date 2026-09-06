from fastapi import APIRouter , status , Response , HTTPException , Depends 
from .. import schemas
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..database import get_db
from ..utils import hashed_password
from .. import models

router = APIRouter(prefix="/users" , tags=["Users"])

@router.post("/signup" , response_model=schemas.ReturnSignupUser )
async def SignupUser(payload : schemas.SignupUser , response : Response , db : Session=Depends(get_db)):
    existing =  db.execute(select(models.User).where(models.User.Email == payload.Email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT , detail="Email already registered")
    payload.Password = hashed_password(payload.Password)
    new_user = models.User(**payload.model_dump())
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    response.status_code = status.HTTP_201_CREATED
    return new_user