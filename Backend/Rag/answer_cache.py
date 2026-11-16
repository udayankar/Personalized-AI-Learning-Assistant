import hashlib
import json
import logging
import os
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from App.database import SessionLocal
from App.models import AnswerCache
from App.schemas import Query_Ans
from .relevance import EMBEDDING_MODEL_NAME

logger = logging.getLogger(__name__)
DEFAULT_TTL_SECONDS = 24 * 60 * 60
PIPELINE_VERSION = "rag-document-only-v4"

def _ttl_seconds() -> int:
    value = os.getenv("ANSWER_CACHE_TTL_SECONDS", str(DEFAULT_TTL_SECONDS))
    try:
        ttl = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("ANSWER_CACHE_TTL_SECONDS must be a positive integer") from error
    if ttl <= 0:
        raise ValueError("ANSWER_CACHE_TTL_SECONDS must be a positive integer")
    return ttl


def Normalize_query(query: str) -> str:
    normalized = unicodedata.normalize("NFC", query)
    return re.sub(r"\s+", " ", normalized.strip()).casefold()


def Query_hash(query: str) -> str:
    return hashlib.sha256(Normalize_query(query).encode("utf-8")).hexdigest()

def Pipeline_fingerprint(generator, relevance_threshold: float) -> str:
    payload = {
        "version": PIPELINE_VERSION,
        "generator_model": getattr(generator, "MODEL_NAME", "unknown"),
        "prompts": [
            getattr(generator, "EVIDENCE_SYSTEM_INSTRUCTION", "unknown"),
            getattr(generator, "DOCUMENT_SYSTEM_INSTRUCTION", "unknown"),
            getattr(generator, "VERIFICATION_SYSTEM_INSTRUCTION", "unknown"),
        ],
        "embedding_model": EMBEDDING_MODEL_NAME,
        "retrieval_metric": "squared_l2",
        "retrieval_top_k": 5,
        "relevance_threshold": float(relevance_threshold),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def Knowledge_base_fingerprint(user_id: int, ready_document_hashes: dict[str, str],
                               pipeline_version: str) -> str:
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("A valid user ID is required for the knowledge-base fingerprint")
    if not isinstance(ready_document_hashes, dict):
        raise ValueError("READY document hashes must be a mapping")
    if any(
        not isinstance(filename, str) or not filename
        or not isinstance(digest, str) or not digest
        for filename, digest in ready_document_hashes.items()
    ):
        raise ValueError("READY document metadata is invalid")
    documents = []
    for filename, digest in sorted(ready_document_hashes.items()):
        documents.append((filename, digest.lower()))
    payload = {
        "user_id": user_id,
        "pipeline_version": pipeline_version,
        "documents": documents,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validated_payload(row, current_sources: dict[str, dict]):
    payload = {
        "answer": row.answer,
        "answer_mode": row.answer_mode,
        "message": row.message,
        "reliability": row.reliability,
        "conflict_status": row.conflict_status,
        "fallback_reason": row.fallback_reason,
        "claims": row.claims,
        "sources": row.sources,
    }
    try:
        validated = Query_Ans.model_validate(payload)
    except Exception:
        return None
    if not validated.answer.strip():
        return None
    if validated.answer_mode == "DOCUMENT_SUPPORTED":
        if not validated.sources:
            return None
        for source in validated.sources:
            current = current_sources.get(source.reference)
            if current is None or source.model_dump() != current:
                return None
        for claim in validated.claims:
            if not claim.sources:
                return None
            for source in claim.sources:
                current = current_sources.get(source.reference)
                if current is None or source.model_dump() != current:
                    return None
    elif validated.answer_mode == "INSUFFICIENT_CONFIDENCE":
        if (
            validated.sources or validated.claims
            or validated.fallback_reason not in {
                "NO_DOCUMENTS_UPLOADED", "NO_SUFFICIENT_DOCUMENT_EVIDENCE"
            }
        ):
            return None
    elif validated.sources or validated.claims:
        return None
    return validated.model_dump()


def Lookup(user_id: int, query_hash: str, context_fingerprint: str,
           pipeline_version: str, current_sources: dict[str, dict]):
    started = time.perf_counter()
    try:
        _ttl_seconds()
        now = datetime.now(timezone.utc)
        with SessionLocal() as session:
            row = session.scalars(select(AnswerCache).where(
                AnswerCache.user_id == user_id,
                AnswerCache.normalized_query_hash == query_hash,
                AnswerCache.context_fingerprint == context_fingerprint,
                AnswerCache.pipeline_version == pipeline_version,
            ).limit(1)).first()
            if row is None:
                reason = "miss"
                payload = None
            elif (row.expires_at.replace(tzinfo=timezone.utc)
                  if row.expires_at.tzinfo is None else row.expires_at) <= now:
                reason = "expired"
                payload = None
            else:
                payload = _validated_payload(row, current_sources)
                reason = "hit" if payload is not None else "invalid_payload_or_provenance"
                if payload is None:
                    session.delete(row)
                    session.commit()
        return payload, reason, (time.perf_counter() - started) * 1000, (
            int(row.gemini_calls) if payload is not None else 0
        )
    except Exception as error:
        logger.warning("answer_cache operation=lookup failed error_type=%s", type(error).__name__)
        return None, "cache_error", (time.perf_counter() - started) * 1000, 0


def Store(user_id: int, query_hash: str, context_fingerprint: str,
          pipeline_version: str, result, gemini_calls: int) -> bool:
    cacheable_no_information = (
        result.answer_mode == "INSUFFICIENT_CONFIDENCE"
        and result.fallback_reason in {
            "NO_DOCUMENTS_UPLOADED", "NO_SUFFICIENT_DOCUMENT_EVIDENCE"
        }
        and not result.sources and not result.claims
    )
    if result.answer_mode != "DOCUMENT_SUPPORTED" and not cacheable_no_information:
        return False
    try:
        payload = Query_Ans.model_validate({
            "answer": result.answer,
            "answer_mode": result.answer_mode,
            "message": result.message,
            "reliability": result.reliability,
            "conflict_status": result.conflict_status,
            "fallback_reason": result.fallback_reason,
            "claims": result.claims,
            "sources": result.sources,
        })
        if not payload.answer.strip() or (
            payload.answer_mode == "DOCUMENT_SUPPORTED" and not payload.sources
        ):
            return False
        ttl = _ttl_seconds()
        now = datetime.now(timezone.utc)
        with SessionLocal() as session:
            expired_ids = session.scalars(
                select(AnswerCache.id).where(
                    AnswerCache.user_id == user_id,
                    AnswerCache.expires_at <= now,
                ).limit(100)
            ).all()
            if expired_ids:
                session.execute(delete(AnswerCache).where(AnswerCache.id.in_(expired_ids)))
            session.add(AnswerCache(
                user_id=user_id,
                normalized_query_hash=query_hash,
                answer=payload.answer,
                answer_mode=payload.answer_mode,
                message=payload.message,
                reliability=payload.reliability,
                conflict_status=payload.conflict_status,
                fallback_reason=payload.fallback_reason,
                claims=[item.model_dump() for item in payload.claims],
                sources=[item.model_dump() for item in payload.sources],
                context_fingerprint=context_fingerprint,
                pipeline_version=pipeline_version,
                gemini_calls=max(0, int(gemini_calls)),
                created_at=now,
                expires_at=now + timedelta(seconds=ttl),
            ))
            session.commit()
        return True
    except IntegrityError:
        return False
    except Exception as error:
        logger.warning("answer_cache operation=store failed error_type=%s", type(error).__name__)
        return False

