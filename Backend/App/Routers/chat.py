from fastapi import APIRouter , Response , HTTPException , status, Depends
from types import SimpleNamespace
from ..schemas import Query_Chat , Query_Ans
from ..oauth2 import get_current_user
from Rag.rag import Ask_question

router = APIRouter(prefix="/chat" , tags=["Chat"])

@router.post("/query" , response_model=Query_Ans)
async def Give_Query(payload : Query_Chat, current_user = Depends(get_current_user)) :
    try:
        result = Ask_question(payload.query, current_user.ID)
        if isinstance(result, tuple):
            answer, sources = result
            result = SimpleNamespace(
                answer=answer,
                answer_mode="DOCUMENT_SUPPORTED" if sources else "INSUFFICIENT_CONFIDENCE",
                message=None,
                reliability="MODERATE" if sources else "LOW",
                conflict_status="NONE",
                fallback_reason=None,
                claims=[],
                sources=sources,
            )
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
    except Exception :
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR , detail="An error occurred while processing the query")

