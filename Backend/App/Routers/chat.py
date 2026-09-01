from fastapi import APIRouter , Response , HTTPException , status
from schemas import Query_Chat , Query_Ans
from Rag.rag import Ask_question

router = APIRouter(prefix="/chat" , tags=["Chat"])

@router.post("/query" , response_model=Query_Ans)
async def Give_Query(payload : Query_Chat) :
    try : 
        answer, results = Ask_question(payload.query) 
        if answer :
            return {
                "answer": answer,
                "sources": results
            }
        else :
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE , detail="Failed to generate answer")
    except Exception :
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR , detail="An error occurred while processing the query")
    