from dataclasses import dataclass
from typing import Any


CLAIM_CLASSIFICATIONS = {
    "SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "CONTRADICTED", "UNCERTAIN"
}
EVIDENCE_RELATIONS = {
    "AGREEMENT", "COMPLEMENTARY", "CONTRADICTION", "DIFFERENT_CONTEXT", "UNCERTAIN"
}


@dataclass(frozen=True)
class EvidenceAssessment:
    coverage_status: str
    required_facts: tuple[dict[str, Any], ...]
    missing_facts: tuple[str, ...]
    relationships: tuple[dict[str, Any], ...]
    sufficient: bool


@dataclass(frozen=True)
class VerifiedAnswer:
    answer: str
    citations: tuple[str, ...]
    claims: tuple[dict[str, Any], ...]
    reliability: str
    conflict_status: str
    disclosure: str | None


def Validate_evidence_assessment(raw, reference_documents) -> EvidenceAssessment | None:
    """Validate coverage and reference IDs returned by the evidence assessor."""
    if not isinstance(raw, dict):
        return None
    status = raw.get("coverage_status")
    if not isinstance(status, str) or status not in {
        "COMPLETE", "PARTIAL", "INSUFFICIENT", "UNCERTAIN"
    }:
        return None
    facts = raw.get("required_facts")
    missing = raw.get("missing_facts")
    relationships = raw.get("relationships")
    if not isinstance(facts, list) or not isinstance(missing, list) or not isinstance(relationships, list):
        return None

    normalized_facts = []
    fact_ids = set()
    all_facts_covered = bool(facts)
    for fact in facts:
        if not isinstance(fact, dict):
            return None
        fact_id = fact.get("fact_id")
        description = fact.get("description")
        refs = fact.get("reference_ids")
        if not isinstance(fact_id, str) or not fact_id or fact_id in fact_ids:
            return None
        if not isinstance(description, str) or not description.strip() or not isinstance(refs, list):
            return None
        fact_ids.add(fact_id)
        valid_refs = list(dict.fromkeys(
            ref for ref in refs
            if isinstance(ref, str) and ref in reference_documents
        ))
        if len(valid_refs) != len(refs) or not valid_refs:
            all_facts_covered = False
        normalized_facts.append({
            "fact_id": fact_id,
            "description": description.strip(),
            "reference_ids": valid_refs,
        })

    if any(not isinstance(item, str) or not item.strip() for item in missing):
        return None
    normalized_relationships = []
    for relation in relationships:
        if not isinstance(relation, dict):
            return None
        relation_type = relation.get("relation")
        refs = relation.get("reference_ids")
        explanation = relation.get("explanation")
        if (
            not isinstance(relation_type, str)
            or relation_type not in EVIDENCE_RELATIONS
            or not isinstance(refs, list)
        ):
            return None
        if not isinstance(explanation, str) or not explanation.strip():
            return None
        valid_refs = list(dict.fromkeys(
            ref for ref in refs
            if isinstance(ref, str) and ref in reference_documents
        ))
        if len(valid_refs) != len(refs) or len(valid_refs) < 2:
            return None
        if relation_type == "CONTRADICTION" and len({
            reference_documents[ref] for ref in valid_refs
        }) < 2:
            return None
        normalized_relationships.append({
            "relation": relation_type,
            "reference_ids": valid_refs,
            "explanation": explanation.strip(),
        })

    sufficient = status == "COMPLETE" and all_facts_covered and not missing
    return EvidenceAssessment(
        coverage_status=status,
        required_facts=tuple(normalized_facts),
        missing_facts=tuple(item.strip() for item in missing),
        relationships=tuple(normalized_relationships),
        sufficient=sufficient,
    )


def Validate_claim_verification(
    claims, raw, reference_documents, evidence_relationships=()
) -> VerifiedAnswer | None:
    """Accept only claims whose exact cited references pass independent verification."""
    if not isinstance(claims, list) or not claims or not isinstance(raw, dict):
        return None
    claim_results = raw.get("claim_results")
    relationships = raw.get("relationships")
    if not isinstance(claim_results, list) or not isinstance(relationships, list):
        return None

    claims_by_id = {}
    for claim in claims:
        if not isinstance(claim, dict):
            return None
        claim_id = claim.get("claim_id")
        text = claim.get("text")
        refs = claim.get("citation_ids")
        if (
            not isinstance(claim_id, str) or not claim_id or claim_id in claims_by_id
            or not isinstance(text, str) or not text.strip() or not isinstance(refs, list)
            or any(not isinstance(ref, str) or ref not in reference_documents for ref in refs)
        ):
            return None
        claims_by_id[claim_id] = {**claim, "text": text.strip(), "citation_ids": refs}

    if len(claim_results) != len(claims_by_id):
        return None
    result_by_id = {}
    for result in claim_results:
        if not isinstance(result, dict):
            return None
        claim_id = result.get("claim_id")
        classification = result.get("classification")
        refs = result.get("citation_ids")
        if (
            not isinstance(claim_id, str)
            or claim_id not in claims_by_id or claim_id in result_by_id
            or not isinstance(classification, str)
            or classification not in CLAIM_CLASSIFICATIONS
            or not isinstance(refs, list)
        ):
            return None
        original_refs = set(claims_by_id[claim_id]["citation_ids"])
        if any(
            not isinstance(ref, str) or ref not in original_refs or ref not in reference_documents
            for ref in refs
        ):
            return None
        valid_refs = list(dict.fromkeys(refs))
        qualified_text = result.get("qualified_text")
        if classification == "SUPPORTED" and not valid_refs:
            return None
        if classification == "PARTIALLY_SUPPORTED":
            if not valid_refs or not isinstance(qualified_text, str) or not qualified_text.strip():
                return None
        if classification == "CONTRADICTED" and not valid_refs:
            return None
        result_by_id[claim_id] = {
            "classification": classification,
            "citation_ids": valid_refs,
            "qualified_text": qualified_text.strip() if isinstance(qualified_text, str) else None,
        }

    verified_relationships = []
    for relation in relationships:
        if not isinstance(relation, dict):
            return None
        relation_type = relation.get("relation")
        claim_ids = relation.get("claim_ids")
        refs = relation.get("citation_ids")
        explanation = relation.get("explanation")
        if (
            not isinstance(relation_type, str)
            or relation_type not in EVIDENCE_RELATIONS
            or not isinstance(claim_ids, list) or len(claim_ids) < 2
            or any(not isinstance(claim_id, str) for claim_id in claim_ids)
            or any(claim_id not in result_by_id for claim_id in claim_ids)
            or not isinstance(refs, list)
            or not isinstance(explanation, str) or not explanation.strip()
        ):
            return None
        allowed_refs = {
            ref for claim_id in claim_ids
            for ref in result_by_id[claim_id]["citation_ids"]
        }
        if any(not isinstance(ref, str) or ref not in allowed_refs for ref in refs):
            return None
        refs = list(dict.fromkeys(refs))
        if len(refs) < 2:
            return None
        distinct_documents = {reference_documents[ref] for ref in refs}
        if relation_type == "CONTRADICTION" and len(distinct_documents) < 2:
            return None
        verified_relationships.append({
            "relation": relation_type,
            "claim_ids": list(dict.fromkeys(claim_ids)),
            "citation_ids": refs,
            "explanation": explanation.strip(),
        })

    accepted_claims = []
    all_supported = True
    for claim_id, claim in claims_by_id.items():
        result = result_by_id[claim_id]
        classification = result["classification"]
        if classification in {"SUPPORTED", "PARTIALLY_SUPPORTED"}:
            text = (
                result["qualified_text"]
                if classification == "PARTIALLY_SUPPORTED"
                else claim["text"]
            )
            accepted_claims.append({
                "claim_id": claim_id,
                "text": text,
                "citation_ids": result["citation_ids"],
                "classification": classification,
            })
            if classification != "SUPPORTED":
                all_supported = False
        else:
            all_supported = False

    if not accepted_claims:
        conflict = any(
            item["relation"] == "CONTRADICTION" for item in verified_relationships
        )
        uncertain = any(
            item["relation"] == "UNCERTAIN" for item in verified_relationships
        )
        return VerifiedAnswer(
            answer="",
            citations=(),
            claims=(),
            reliability="LOW",
            conflict_status="CONTRADICTION" if conflict else ("UNCERTAIN" if uncertain else "NONE"),
            disclosure="No generated document claim could be verified against its cited evidence.",
        )

    accepted_reference_ids = {
        ref for claim in accepted_claims for ref in claim["citation_ids"]
    }
    represented_document_ids = {
        reference_documents[ref]
        for ref in accepted_reference_ids
        if ref in reference_documents
    }
    assessment_conflict = False
    assessment_uncertain = False
    incomplete_assessment_conflict = False
    for relation in evidence_relationships:
        relation_type = relation.get("relation")
        refs = relation.get("reference_ids", [])
        if (
            relation_type not in EVIDENCE_RELATIONS
            or not isinstance(refs, (list, tuple))
            or len(refs) < 2
            or any(ref not in reference_documents for ref in refs)
        ):
            continue
        relation_document_ids = {reference_documents[ref] for ref in refs}
        if relation_type == "CONTRADICTION" and len(relation_document_ids) > 1:
            if (
                relation_document_ids.issubset(represented_document_ids)
                and set(refs).issubset(accepted_reference_ids)
            ):
                assessment_conflict = True
            else:
                incomplete_assessment_conflict = True
        elif relation_type == "UNCERTAIN":
            assessment_uncertain = True

    if incomplete_assessment_conflict:
        return VerifiedAnswer(
            answer="",
            citations=(),
            claims=(),
            reliability="LOW",
            conflict_status="CONTRADICTION",
            disclosure=(
                "The evidence assessment found conflicting document statements, but the "
                "generated answer did not preserve both sides."
            ),
        )

    conflict = assessment_conflict or any(
        item["relation"] == "CONTRADICTION" for item in verified_relationships
    )
    uncertain_relation = assessment_uncertain or any(
        item["relation"] == "UNCERTAIN" for item in verified_relationships
    )
    citation_ids = list(dict.fromkeys(
        ref for claim in accepted_claims for ref in claim["citation_ids"]
    ))
    if conflict:
        reliability = "MODERATE"
        disclosure = (
            "The retrieved documents make conflicting claims. Both statements are shown with "
            "their sources; the documents do not establish which is correct."
        )
    elif all_supported and not uncertain_relation:
        reliability = "HIGH"
        disclosure = None
    elif any(item["relation"] == "UNCERTAIN" for item in verified_relationships):
        reliability = "MODERATE"
        disclosure = "The relationship between some retrieved statements could not be determined reliably."
    else:
        reliability = "MODERATE" if accepted_claims else "LOW"
        disclosure = (
            "Some generated claims could not be verified and were omitted or qualified."
        )

    return VerifiedAnswer(
        answer="\n\n".join(claim["text"] for claim in accepted_claims),
        citations=tuple(citation_ids),
        claims=tuple(accepted_claims),
        reliability=reliability,
        conflict_status="CONTRADICTION" if conflict else (
            "UNCERTAIN" if uncertain_relation else "NONE"
        ),
        disclosure=disclosure,
    )
