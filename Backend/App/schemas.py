from pydantic import BaseModel

class Query_Chat(BaseModel) :
    query : str

class Source(BaseModel):
    source: str
    page: int
    text: str

class Query_Ans(BaseModel) :
    answer : str
    sources: list[Source]

