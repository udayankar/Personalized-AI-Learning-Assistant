from fastapi import APIRouter , Response , HTTPException , status, Depends
from starlette.concurrency import run_in_threadpool
from ..schemas import Query_Chat , Query_Ans
from ..oauth2 import get_current_user
from Rag.rag import Ask_question, RAGProcessingError
from ..rate_limit import user_rate_limit

router = APIRouter(prefix="/chat" , tags=["Chat"])

@router.post("/query" , response_model=Query_Ans,
             dependencies=[Depends(user_rate_limit("chat"))])
async def Give_Query(payload : Query_Chat, current_user = Depends(get_current_user)) :
    try:
        result = await run_in_threadpool(Ask_question, payload.query, current_user.ID)
        if result.answer:
            return {
                "answer": result.answer,
                "answer_mode": result.answer_mode,
                "message": result.message,
                "reliability": result.reliability,
                "conflict_status": result.conflict_status,
                "fallback_reason": result.fallback_reason,
                "claims": result.claims,
                "sources": result.sources,
            }
        else:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE , detail="Failed to generate answer")
    except HTTPException:
        raise
    except RAGProcessingError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document-based answering is temporarily unavailable. Please try again.",
        )
    except Exception :
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR , detail="An error occurred while processing the query")

