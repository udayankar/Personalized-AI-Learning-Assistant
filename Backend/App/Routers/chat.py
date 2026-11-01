from fastapi import APIRouter , Response , HTTPException , status, Depends
from ..schemas import Query_Chat , Query_Ans
from ..oauth2 import get_current_user
from Rag.rag import Ask_question

router = APIRouter(prefix="/chat" , tags=["Chat"])

@router.post("/query" , response_model=Query_Ans)
async def Give_Query(payload : Query_Chat, current_user = Depends(get_current_user)) :
    try : 
        answer , results = Ask_question(payload.query) 
        if answer :
            return {
                "answer": answer,
                "sources": results
            }
        else :
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE , detail="Failed to generate answer")
    except HTTPException:
        raise
    except Exception :
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR , detail="An error occurred while processing the query")

