import hashlib
import re
from dataclasses import dataclass

from .answering import Validate_claim_verification, Validate_evidence_assessment
from .vector_store import Load_vector_store, Retrieve
from .embedder import model
from .generator import (
    Assess_document_evidence,
    Generate_claims,
    Generate_general_answer,
    Verify_document_claims,
)


DOCUMENT_SUPPORTED = "DOCUMENT_SUPPORTED"
GENERAL_KNOWLEDGE = "GENERAL_KNOWLEDGE"
INSUFFICIENT_CONFIDENCE = "INSUFFICIENT_CONFIDENCE"

NO_SUFFICIENT_DOCUMENT_EVIDENCE = "NO_SUFFICIENT_DOCUMENT_EVIDENCE"
DOCUMENT_GENERATION_DECLINED = "DOCUMENT_GENERATION_DECLINED"
CITATION_VERIFICATION_FAILED = "CITATION_VERIFICATION_FAILED"
DOCUMENT_GENERATION_FAILED = "DOCUMENT_GENERATION_FAILED"
DOCUMENT_ANSWER_UNRELIABLE = "DOCUMENT_ANSWER_UNRELIABLE"
GENERAL_KNOWLEDGE_UNRELIABLE = "GENERAL_KNOWLEDGE_UNRELIABLE"
EVIDENCE_ASSESSMENT_FAILED = "EVIDENCE_ASSESSMENT_FAILED"


FALLBACK_MESSAGES = {
    NO_SUFFICIENT_DOCUMENT_EVIDENCE: (
        "The uploaded documents do not sufficiently cover this question. "
        "The following explanation is based on general model knowledge and has not been externally verified."
    ),
    DOCUMENT_GENERATION_DECLINED: (
        "The retrieved passages did not support a document-based answer. "
        "The following explanation is based on general model knowledge and has not been externally verified."
    ),
    CITATION_VERIFICATION_FAILED: (
        "I could not verify the generated claims against their cited passages. "
        "The following explanation is based on general model knowledge and has not been externally verified."
    ),
    DOCUMENT_GENERATION_FAILED: (
        "I could not generate a reliable document-based answer. "
        "The following explanation is based on general model knowledge and has not been externally verified."
    ),
    DOCUMENT_ANSWER_UNRELIABLE: (
        "The retrieved passages did not support a reliable document-based answer. "
        "The following explanation is based on general model knowledge and has not been externally verified."
    ),
    EVIDENCE_ASSESSMENT_FAILED: (
        "I could not assess document coverage reliably. "
        "The following explanation is based on general model knowledge and has not been externally verified."
    ),
}

INSUFFICIENT_MESSAGES = {
    GENERAL_KNOWLEDGE_UNRELIABLE: (
        "The documents do not provide sufficient evidence, and a reliable general answer could not be produced. "
        "Try narrowing the question or uploading relevant material."
    ),
    CITATION_VERIFICATION_FAILED: (
        "The document-based claims could not be verified, and a reliable general answer could not be produced. "
        "Try narrowing the question or uploading relevant material."
    ),
}


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
        """Keep tuple unpacking available to internal callers during the response transition."""
        yield self.answer
        yield self.sources


def _insufficient_result(reason):
    return AnswerResult(
        answer="I can't provide a reliable answer from the available information.",
        answer_mode=INSUFFICIENT_CONFIDENCE,
        message=INSUFFICIENT_MESSAGES.get(
            reason,
            "The available information is insufficient for a reliable answer. Try narrowing the question or uploading relevant material.",
        ),
        sources=[],
        claims=[],
        reliability="LOW",
        conflict_status="UNCERTAIN",
        fallback_reason=reason,
    )


def _general_knowledge_result(question, reason):
    try:
        generated = Generate_general_answer(question)
    except Exception:
        return _insufficient_result(GENERAL_KNOWLEDGE_UNRELIABLE)
    if (
        not isinstance(generated, dict)
        or generated.get("can_answer") is not True
        or not isinstance(generated.get("answer"), str)
        or not generated["answer"].strip()
    ):
        return _insufficient_result(GENERAL_KNOWLEDGE_UNRELIABLE)
    return AnswerResult(
        answer=generated["answer"].strip(),
        answer_mode=GENERAL_KNOWLEDGE,
        message=FALLBACK_MESSAGES[reason],
        sources=[],
        claims=[],
        reliability="MODERATE",
        conflict_status="NONE",
        fallback_reason=reason,
    )


def _passage_bundle(retrieval):
    passages = []
    reference_map = {}
    reference_documents = {}
    for position, chunk in enumerate(retrieval.relevant_chunks, start=1):
        model_reference = f"R{position}"
        stable_reference = "passage-" + hashlib.sha256(
            f"{retrieval.user_id}\0{chunk.document_id}\0{chunk.page}\0{chunk.text}".encode("utf-8")
        ).hexdigest()[:16]
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


def _document_answer(question, retrieval):
    passages, reference_map, reference_documents = _passage_bundle(retrieval)
    try:
        raw_assessment = Assess_document_evidence(question, passages)
    except Exception:
        return None, EVIDENCE_ASSESSMENT_FAILED
    assessment = Validate_evidence_assessment(raw_assessment, reference_documents)
    if assessment is None:
        return None, EVIDENCE_ASSESSMENT_FAILED
    if not assessment.sufficient:
        return None, NO_SUFFICIENT_DOCUMENT_EVIDENCE

    assessment_payload = {
        "coverage_status": assessment.coverage_status,
        "required_facts": list(assessment.required_facts),
        "missing_facts": list(assessment.missing_facts),
        "relationships": list(assessment.relationships),
    }
    try:
        generated = Generate_claims(question, passages, assessment_payload)
    except Exception:
        return None, DOCUMENT_GENERATION_FAILED
    claims, claim_error = _valid_generated_claims(generated, reference_documents)
    if claims is None:
        return None, claim_error

    try:
        verification = Verify_document_claims(question, claims, passages)
    except Exception:
        return None, CITATION_VERIFICATION_FAILED
    verified = Validate_claim_verification(
        claims,
        verification,
        reference_documents,
        evidence_relationships=assessment.relationships,
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


def Ask_question(question, user_id: int):
    index, chunks = Load_vector_store(user_id)
    if index is None or not chunks:
        return _general_knowledge_result(question, NO_SUFFICIENT_DOCUMENT_EVIDENCE)

    retrieval = Retrieve(question, index, chunks, model, user_id, k=5)
    if not retrieval.evidence_sufficient:
        return _general_knowledge_result(question, NO_SUFFICIENT_DOCUMENT_EVIDENCE)
    document_result, fallback_reason = _document_answer(question, retrieval)
    if document_result is not None:
        return document_result
    return _general_knowledge_result(question, fallback_reason)


if __name__ == "__main__":
    raise SystemExit("RAG queries require an authenticated database user ID.")
