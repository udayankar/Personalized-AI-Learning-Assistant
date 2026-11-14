from pydantic import BaseModel , ConfigDict , EmailStr , Field
from typing import Literal
from datetime import datetime

class Query_Chat(BaseModel) :
    query : str

class Source(BaseModel) :
    reference: str
    source : str
    page : int | None = None
    text : str

class AnswerClaim(BaseModel):
    text: str
    classification: Literal["SUPPORTED", "PARTIALLY_SUPPORTED"]
    sources: list[Source]

class Query_Ans(BaseModel) :
    answer : str
    answer_mode: Literal["DOCUMENT_SUPPORTED", "GENERAL_KNOWLEDGE", "INSUFFICIENT_CONFIDENCE"]
    message: str | None = None
    reliability: Literal["HIGH", "MODERATE", "LOW"]
    conflict_status: Literal["NONE", "CONTRADICTION", "UNCERTAIN"]
    fallback_reason: str | None = None
    claims: list[AnswerClaim] = Field(default_factory=list)
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
