from pydantic import BaseModel , ConfigDict , EmailStr , Field
from datetime import datetime

class Query_Chat(BaseModel) :
    query : str

class Source(BaseModel) :
    source : str
    page : int
    text : str

class Query_Ans(BaseModel) :
    answer : str
    sources : list[Source]

class Signup_User(BaseModel) :
    Name : str = Field(min_length=1 , max_length=100)
    Email : EmailStr
    Password : str = Field(min_length=8 , max_length=128)

class Login_User(BaseModel) :
    Email : EmailStr
    Password : str = Field(min_length=1 , max_length=128)

class Return_Signup_User(BaseModel) :
    ID : int
    Name : str
    Email : EmailStr
    Created_at : datetime

    model_config = ConfigDict(from_attributes=True)