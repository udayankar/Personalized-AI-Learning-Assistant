import hashlib
import logging
import re
import time
from dataclasses import dataclass, replace
from sqlalchemy import select
from App.database import SessionLocal
from App.models import Document
from . import answer_cache, generator
from .answering import Validate_claim_verification
from .answering import Validate_evidence_assessment
from .vector_store import Load_ready_chunk_metadata, Retrieve
from .embedder import embedding_provider
from .relevance import Get_calibrated_relevance_threshold
from .generator import (
    Assess_document_evidence,  # Offline evaluation helper; not called by the query path.
    Generate_claims,
    Verify_document_claims,
)


DOCUMENT_SUPPORTED = "DOCUMENT_SUPPORTED"
INSUFFICIENT_CONFIDENCE = "INSUFFICIENT_CONFIDENCE"

NO_DOCUMENTS_UPLOADED = "NO_DOCUMENTS_UPLOADED"
NO_SUFFICIENT_DOCUMENT_EVIDENCE = "NO_SUFFICIENT_DOCUMENT_EVIDENCE"
DOCUMENT_GENERATION_DECLINED = "DOCUMENT_GENERATION_DECLINED"
CITATION_VERIFICATION_FAILED = "CITATION_VERIFICATION_FAILED"
DOCUMENT_ANSWER_UNRELIABLE = "DOCUMENT_ANSWER_UNRELIABLE"
logger = logging.getLogger(__name__)


class RAGProcessingError(RuntimeError):
    """A document-answering operation failed for technical reasons."""


def get_ready_document_hashes(user_id: int) -> dict[str, str]:
    with SessionLocal() as session:
        rows = session.execute(
            select(Document.id, Document.sha256).where(
                Document.user_id == user_id,
                Document.status == "READY",
            )
        ).all()
    return {filename: digest for filename, digest in rows}


NO_DOCUMENTS_MESSAGE = "You haven't uploaded any documents yet. Upload a document to start asking questions."
NO_INFORMATION_MESSAGE = "No relevant information was found in your uploaded documents to answer this question."


@dataclass(frozen=True)
class AnswerResult:
    answer: str
    answer_mode: str
    message: str | None
    sources: list[dict]
    claims: list[dict]
    reliability: str
    conflict_status: str
    fallback_reason: str | None

    def __iter__(self):
        yield self.answer
        yield self.sources


def _no_information_result(reason):
    message = NO_DOCUMENTS_MESSAGE if reason == NO_DOCUMENTS_UPLOADED else NO_INFORMATION_MESSAGE
    return AnswerResult(
        answer=message,
        answer_mode=INSUFFICIENT_CONFIDENCE,
        message=None,
        sources=[],
        claims=[],
        reliability="LOW",
        conflict_status="NONE",
        fallback_reason=reason,
    )


def _passage_bundle(retrieval):
    passages = []
    reference_map = {}
    reference_documents = {}
    for position, chunk in enumerate(retrieval.chunks, start=1):
        model_reference = f"R{position}"
        stable_reference = _stable_passage_reference(
            retrieval.user_id, chunk.document_id, chunk.page, chunk.text
        )
        passage = {
            "reference": model_reference,
            "source": chunk.source,
            "page": chunk.page,
            "text": chunk.text,
        }
        passages.append(passage)
        reference_map[model_reference] = {
            "reference": stable_reference,
            "source": chunk.source,
            "page": chunk.page,
            "text": chunk.text,
        }
        reference_documents[model_reference] = chunk.document_id
    return passages, reference_map, reference_documents


def _stable_passage_reference(user_id, document_id, page, text):
    return "passage-" + hashlib.sha256(
        f"{user_id}\0{document_id}\0{page}\0{text}".encode("utf-8")
    ).hexdigest()[:16]


def _current_source_map(chunks, user_id, ready_document_ids):
    current = {}
    for chunk in chunks:
        document_id = chunk.get("document_id", chunk.get("source"))
        if (
            not isinstance(document_id, str)
            or document_id not in ready_document_ids
            or chunk.get("user_id", user_id) != user_id
            or not isinstance(chunk.get("text"), str)
        ):
            continue
        page = chunk.get("page")
        if page is not None and (isinstance(page, bool) or not isinstance(page, int)):
            page = None
        source = str(chunk.get("source", "Unknown"))
        reference = _stable_passage_reference(user_id, document_id, page, chunk["text"])
        current[reference] = {
            "reference": reference,
            "source": source,
            "page": page,
            "text": chunk["text"],
        }
    return current


def _valid_generated_claims(raw, reference_documents):
    if not isinstance(raw, dict) or not isinstance(raw.get("claims"), list) or not raw["claims"]:
        return None, DOCUMENT_GENERATION_DECLINED
    claim_ids = set()
    claims = []
    for claim in raw["claims"]:
        if not isinstance(claim, dict):
            return None, DOCUMENT_GENERATION_DECLINED
        claim_id = claim.get("claim_id")
        text = claim.get("text")
        refs = claim.get("citation_ids")
        if (
            not isinstance(claim_id, str) or not claim_id or claim_id in claim_ids
            or not isinstance(text, str) or not text.strip() or not isinstance(refs, list)
            or not refs
        ):
            return None, DOCUMENT_GENERATION_DECLINED
        if any(not isinstance(ref, str) or ref not in reference_documents for ref in refs):
            return None, CITATION_VERIFICATION_FAILED
        claim_ids.add(claim_id)
        claims.append({
            "claim_id": claim_id,
            "text": re.sub(r"\[\s*R\d+\s*\]", "", text).strip(),
            "citation_ids": list(dict.fromkeys(refs)),
        })
    if any(not claim["text"] for claim in claims):
        return None, DOCUMENT_GENERATION_DECLINED
    return claims, None


def _document_answer(question, retrieval, gemini_call_count=None):
    passages, reference_map, reference_documents = _passage_bundle(retrieval)
    try:
        if gemini_call_count is not None:
            gemini_call_count[0] += 1
        generated = Generate_claims(question, passages)
    except Exception as error:
        logger.warning(
            "rag_processing_failure stage=answer_generation error_type=%s",
            type(error).__name__,
        )
        raise RAGProcessingError("Document answer generation failed") from error
    claims, claim_error = _valid_generated_claims(generated, reference_documents)
    if claims is None:
        return None, claim_error

    try:
        if gemini_call_count is not None:
            gemini_call_count[0] += 1
        verification = Verify_document_claims(question, claims, passages)
    except Exception as error:
        logger.warning(
            "rag_processing_failure stage=claim_verification error_type=%s",
            type(error).__name__,
        )
        raise RAGProcessingError("Document claim verification failed") from error
    verified = Validate_claim_verification(
        claims,
        verification,
        reference_documents,
        evidence_relationships=(),
    )
    if verified is None:
        return None, CITATION_VERIFICATION_FAILED
    if verified.reliability == "LOW":
        return None, DOCUMENT_ANSWER_UNRELIABLE

    sources = [reference_map[ref] for ref in verified.citations]
    source_by_ref = reference_map
    if not sources:
        return None, CITATION_VERIFICATION_FAILED
    claims = [
        {
            "text": claim["text"],
            "classification": claim["classification"],
            "sources": [source_by_ref[ref] for ref in claim["citation_ids"]],
        }
        for claim in verified.claims
    ]
    result = AnswerResult(
        answer=verified.answer,
        answer_mode=DOCUMENT_SUPPORTED,
        message=verified.disclosure,
        sources=sources,
        claims=claims,
        reliability=verified.reliability,
        conflict_status=verified.conflict_status,
        fallback_reason=None,
    )
    return result, None


def _answer_from_cache(payload):
    return AnswerResult(
        answer=payload["answer"],
        answer_mode=payload["answer_mode"],
        message=payload["message"],
        sources=payload["sources"],
        claims=payload["claims"],
        reliability=payload["reliability"],
        conflict_status=payload["conflict_status"],
        fallback_reason=payload["fallback_reason"],
    )


def _ask_question(question, user_id: int):
    chunks = Load_ready_chunk_metadata(user_id)
    ready_document_hashes = get_ready_document_hashes(user_id)
    ready_document_ids = set(ready_document_hashes)
    cache_key = None
    cacheable_index_state = ready_document_ids.issubset({
        chunk.get("document_id", chunk.get("source"))
        for chunk in chunks
        if isinstance(chunk, dict) and chunk.get("user_id", user_id) == user_id
        and isinstance(chunk.get("document_id", chunk.get("source")), str)
    })
    try:
        pipeline_version = answer_cache.Pipeline_fingerprint(
            generator
        )
        context_fingerprint = answer_cache.Knowledge_base_fingerprint(
            user_id, ready_document_hashes, pipeline_version
        )
        current_sources = _current_source_map(chunks, user_id, ready_document_ids)
        query_hash = answer_cache.Query_hash(question)
        cache_key = (query_hash, context_fingerprint, pipeline_version, current_sources)
        if cacheable_index_state:
            cached, reason, lookup_ms, calls_avoided = answer_cache.Lookup(
                user_id, *cache_key
            )
            if cached is not None:
                logger.info(
                    "answer_cache outcome=hit lookup_ms=%.2f gemini_calls_avoided=%d",
                    lookup_ms, calls_avoided,
                )
                return _answer_from_cache(cached)
            logger.info("answer_cache outcome=%s lookup_ms=%.2f", reason, lookup_ms)
        else:
            logger.info("answer_cache outcome=bypass reason=ready_document_chunk_missing")
    except Exception as error:
        logger.warning(
            "answer_cache outcome=bypass reason=fingerprint_error error_type=%s",
            type(error).__name__, exc_info=True,
        )
        cache_key = None

    retrieval = Retrieve(
        question,
        embedding_provider,
        user_id,
        k=5,
        allowed_document_ids=ready_document_ids,
    )
    gemini_call_count = [0]
    if not retrieval.relevant_chunks:
        reason = NO_SUFFICIENT_DOCUMENT_EVIDENCE
        if not ready_document_hashes and not _user_has_documents(user_id):
            reason = NO_DOCUMENTS_UPLOADED
        result = _no_information_result(reason)
    else:
        retrieval = replace(retrieval, chunks=retrieval.relevant_chunks)
        result, fallback_reason = _document_answer(
            question, retrieval, gemini_call_count
        )
        if result is None:
            result = _no_information_result(fallback_reason)

    cacheable_answer = result.answer_mode == DOCUMENT_SUPPORTED or (
        result.answer_mode == INSUFFICIENT_CONFIDENCE
        and result.fallback_reason in {NO_DOCUMENTS_UPLOADED, NO_SUFFICIENT_DOCUMENT_EVIDENCE}
    )
    if cache_key is not None and cacheable_index_state and cacheable_answer:
        answer_cache.Store(
            user_id, cache_key[0], cache_key[1], cache_key[2],
            result, gemini_call_count[0],
        )
    return result


def _user_has_documents(user_id: int) -> bool:
    with SessionLocal() as session:
        return session.scalar(
            select(Document.id).where(Document.user_id == user_id).limit(1)
        ) is not None


def Ask_question(question, user_id: int):
    started = time.perf_counter()
    result = _ask_question(question, user_id)
    logger.info(
        "rag_query complete answer_mode=%s total_ms=%.2f",
        result.answer_mode, (time.perf_counter() - started) * 1000,
    )
    return result


if __name__ == "__main__":
    raise SystemExit("RAG queries require an authenticated database user ID.")
