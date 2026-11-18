import importlib
import hashlib
import os
import sys
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import numpy as np
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


for _module_name in (
    "Rag.rag", "Rag.answer_cache", "Rag.embedder", "Rag.generator",
    "Rag.vector_store", "Rag.user_storage",
):
    sys.modules.pop(_module_name, None)



with patch.dict(os.environ, {"LLM_API_KEY": "unit-test-key"}):
    from App.base import Base
    from App.models import AnswerCache, User, Document, DocumentChunk
    from App.schemas import Query_Ans
    from App.database import engine as application_engine
    from Rag import answer_cache, rag, user_storage, vector_store


class ExactAnswerCacheTests(unittest.TestCase):
    def test_application_engine_does_not_echo_private_sql_parameters(self):
        self.assertFalse(application_engine.echo)
        self.assertTrue(application_engine.hide_parameters)

    def setUp(self):
        self.calibration_patch = patch.object(vector_store, "Get_calibrated_relevance_threshold", return_value=1.0)
        self.calibration_patch.start()
        self.addCleanup(self.calibration_patch.stop)
        self.rag_calibration_patch = patch.object(rag, "Get_calibrated_relevance_threshold", return_value=1.0)
        self.rag_calibration_patch.start()
        self.addCleanup(self.rag_calibration_patch.stop)
        self.store_config_patch = patch.object(vector_store, "get_embedding_configuration", return_value=types.SimpleNamespace(
            dimensions=2, distance_metric="squared_l2", as_dict=lambda: {"provider": "test", "dimensions": 2}
        ))
        self.store_config_patch.start()
        self.addCleanup(self.store_config_patch.stop)
        self.temp_dir = TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.documents_patch = patch.object(user_storage, "DOCUMENTS_ROOT", root / "documents")
        self.storage_patch = patch.object(user_storage, "STORAGE_ROOT", root / "storage")
        self.documents_patch.start()
        self.storage_patch.start()
        self.addCleanup(self.documents_patch.stop)
        self.addCleanup(self.storage_patch.stop)
        self.addCleanup(self.temp_dir.cleanup)

        self.engine = create_engine(
            f"sqlite:///{root / 'cache-test.sqlite'}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.session_factory_patch = patch.object(answer_cache, "SessionLocal", self.Session)
        self.session_factory_patch.start()
        self.addCleanup(self.session_factory_patch.stop)
        self.vector_session_patch = patch.object(vector_store, "SessionLocal", self.Session)
        self.vector_session_patch.start()
        self.addCleanup(self.vector_session_patch.stop)
        self.addCleanup(self.engine.dispose)
        with self.Session() as session:
            session.add_all([
                User(ID=71, Name="Test One", Email="one@example.test", Password="hashed"),
                User(ID=72, Name="Test Two", Email="two@example.test", Password="hashed"),
            ])
            session.commit()

        rag.embedding_provider = types.SimpleNamespace(embed_query=lambda _query: np.array([1.0] + [0.0] * 767))
        self.retrieve_patch = patch.object(rag, "Retrieve", side_effect=self._retrieve)
        self.retrieve_patch.start()
        self.addCleanup(self.retrieve_patch.stop)
        self.ready_document_hashes = {}
        self.ready_document_hashes_patch = patch.object(
            rag, "get_ready_document_hashes",
            side_effect=lambda user_id: self.ready_document_hashes.get(user_id, {}),
        )
        self.ready_document_hashes_patch.start()
        self.addCleanup(self.ready_document_hashes_patch.stop)
        self.no_documents_patch = patch.object(rag, "_user_has_documents", return_value=False)
        self.no_documents_patch.start()
        self.addCleanup(self.no_documents_patch.stop)
        self.assess_patch = patch.object(rag, "Assess_document_evidence", return_value={
            "coverage_status": "COMPLETE",
            "required_facts": [{"fact_id": "F1", "description": "fact", "reference_ids": ["R1"]}],
            "missing_facts": [], "relationships": [],
        })
        self.assess = self.assess_patch.start()
        self.addCleanup(self.assess_patch.stop)
        self.generate_patch = patch.object(rag, "Generate_claims", return_value={
            "claims": [{"claim_id": "C1", "text": "A supported answer", "citation_ids": ["R1"]}],
        })
        self.generate = self.generate_patch.start()
        self.addCleanup(self.generate_patch.stop)
        self.verify_patch = patch.object(rag, "Verify_document_claims", side_effect=lambda _q, claims, _p: {
            "claim_results": [{
                "claim_id": claim["claim_id"], "classification": "SUPPORTED",
                "citation_ids": claim["citation_ids"], "qualified_text": None,
            } for claim in claims],
            "relationships": [],
        })
        self.verify = self.verify_patch.start()
        self.addCleanup(self.verify_patch.stop)

    @staticmethod
    def chunk(source, text, user_id, page=1):
        return {
            "source": source, "document_id": source, "page": page,
            "text": text, "user_id": user_id,
        }

    def save_chunks(self, user_id, chunks, vectors=None):
        grouped_text = {}
        for chunk in chunks:
            document_id = chunk.get("document_id", chunk.get("source"))
            grouped_text.setdefault(document_id, []).append(chunk["text"])
        self.ready_document_hashes[user_id] = {
            document_id: hashlib.sha256("\0".join(texts).encode("utf-8")).hexdigest()
            for document_id, texts in grouped_text.items()
        }
        if vectors is None:
            vectors = np.array([[0.1, 0.0] for _ in chunks], dtype="float32")
        with self.Session() as session:
            for document_id in grouped_text:
                document = session.get(Document, document_id)
                if document is None:
                    document = Document(
                        id=document_id, user_id=user_id, filename=document_id,
                        storage_filename=f"{document_id}-{user_id}", file_size_bytes=1,
                        page_count=1, sha256=self.ready_document_hashes[user_id][document_id], status="READY",
                    )
                    session.add(document)
                    session.flush()
                session.query(DocumentChunk).filter_by(document_id=document_id).delete()
                for index, chunk in enumerate(item for item in chunks if item.get("document_id", item.get("source")) == document_id):
                    vector = np.asarray(vectors[chunks.index(chunk)], dtype="float32").reshape(-1)
                    vector = np.pad(vector, (0, max(0, 768 - vector.size)))[:768]
                    norm = np.linalg.norm(vector)
                    vector = vector / norm if norm else np.eye(1, 768, 0, dtype="float32")[0]
                    session.add(DocumentChunk(
                        user_id=user_id, document_id=document_id, chunk_index=index,
                        text=chunk["text"], page_number=chunk.get("page"), embedding=vector.tolist(),
                        embedding_provider="test", embedding_model="test-model", embedding_dimensions=768,
                        embedding_task_type="RETRIEVAL_DOCUMENT",
                    ))
            session.commit()

    def _retrieve(self, query, _embedder, user_id, k=5, allowed_document_ids=None):
        chunks = vector_store.Load_ready_chunk_metadata(user_id)
        if allowed_document_ids is not None:
            chunks = [chunk for chunk in chunks if chunk["document_id"] in allowed_document_ids]
        for chunk in chunks[:k]:
            chunk["distance"] = 0.1
        return vector_store.Make_retrieval_result(query, user_id, chunks[:k], 1.0)

    def cache_count(self):
        with self.Session() as session:
            return session.scalar(select(func.count()).select_from(AnswerCache))

    def test_exact_hit_uses_same_answer_and_avoids_all_gemini_calls(self):
        self.save_chunks(71, [self.chunk("notes.pdf", "Thresholding separates image pixels by intensity.", 71)])

        first = rag.Ask_question("What is thresholding?", 71)
        second = rag.Ask_question("  What is   thresholding?  ", 71)

        self.assertEqual(first.answer_mode, "DOCUMENT_SUPPORTED")
        self.assertEqual(second.answer, first.answer)
        self.assertEqual(second.sources, first.sources)
        self.assertEqual(self.assess.call_count, 1)
        self.assertEqual(self.generate.call_count, 1)
        self.assertEqual(self.verify.call_count, 1)
        self.assertEqual(self.cache_count(), 1)
        Query_Ans.model_validate({
            "answer": second.answer, "answer_mode": second.answer_mode,
            "message": second.message, "reliability": second.reliability,
            "conflict_status": second.conflict_status,
            "fallback_reason": second.fallback_reason,
            "claims": second.claims, "sources": second.sources,
        })

    def test_distinct_normalized_query_does_not_hit(self):
        self.save_chunks(71, [self.chunk("notes.pdf", "Relevant passage", 71)])
        rag.Ask_question("Define thresholding?", 71)
        rag.Ask_question("Define thresholding!", 71)
        self.assertEqual(self.assess.call_count, 2)

    def test_case_and_whitespace_variants_share_the_cached_answer(self):
        self.save_chunks(71, [self.chunk("notes.pdf", "Relevant passage", 71)])
        retrieve = rag.Retrieve
        with patch.object(rag, "Retrieve", wraps=retrieve) as retrieve_spy:
            first = rag.Ask_question("Explain Python List", 71)
            second = rag.Ask_question("  explain   python list  ", 71)
        self.assertEqual(first.answer, second.answer)
        self.assertEqual(self.assess.call_count, 1)
        self.assertEqual(retrieve_spy.call_count, 1)

    def test_knowledge_base_fingerprint_is_order_independent_and_content_sensitive(self):
        pipeline = "pipeline"
        first = answer_cache.Knowledge_base_fingerprint(
            71, {"a.pdf": "a" * 64, "b.pdf": "b" * 64}, pipeline
        )
        reordered = answer_cache.Knowledge_base_fingerprint(
            71, {"b.pdf": "b" * 64, "a.pdf": "a" * 64}, pipeline
        )
        changed = answer_cache.Knowledge_base_fingerprint(
            71, {"a.pdf": "c" * 64, "b.pdf": "b" * 64}, pipeline
        )
        other_user = answer_cache.Knowledge_base_fingerprint(
            72, {"a.pdf": "a" * 64, "b.pdf": "b" * 64}, pipeline
        )
        self.assertEqual(first, reordered)
        self.assertNotEqual(first, changed)
        self.assertNotEqual(first, other_user)

    def test_no_information_result_is_cached_without_an_answer_generation_call(self):
        retrieve = rag.Retrieve
        with patch.object(rag, "Retrieve", wraps=retrieve) as retrieve_spy:
            first = rag.Ask_question("What is a binary tree?", 71)
            second = rag.Ask_question("What is a binary tree?", 71)
        self.assertEqual(first.answer_mode, "INSUFFICIENT_CONFIDENCE")
        self.assertEqual(first.fallback_reason, "NO_DOCUMENTS_UPLOADED")
        self.assertEqual(second.answer, first.answer)
        self.assertFalse(hasattr(rag, "Generate_general_answer"))
        self.assertEqual(retrieve_spy.call_count, 1)

    def test_no_information_cache_is_invalidated_after_relevant_upload(self):
        first = rag.Ask_question("What is image thresholding?", 71)
        self.assertEqual(first.answer_mode, "INSUFFICIENT_CONFIDENCE")
        self.save_chunks(71, [self.chunk("vision.pdf", "Image thresholding applies a cutoff to pixel intensity.", 71)])

        second = rag.Ask_question("What is image thresholding?", 71)

        self.assertEqual(second.answer_mode, "DOCUMENT_SUPPORTED")
        self.assertEqual(second.sources[0]["source"], "vision.pdf")
        self.assertEqual(self.assess.call_count, 1)

    def test_deleted_cached_source_invalidates_document_answer(self):
        self.save_chunks(71, [self.chunk("old.pdf", "Relevant source passage", 71)])
        first = rag.Ask_question("What does the source say?", 71)
        with self.Session() as session:
            session.delete(session.get(Document, "old.pdf"))
            session.commit()
        self.ready_document_hashes[71] = {}

        second = rag.Ask_question("What does the source say?", 71)

        self.assertEqual(first.answer_mode, "DOCUMENT_SUPPORTED")
        self.assertEqual(second.answer_mode, "INSUFFICIENT_CONFIDENCE")
        self.assertEqual(second.sources, [])

    def test_changed_or_additional_retrieved_evidence_invalidates_document_answer(self):
        self.save_chunks(71, [self.chunk("a.pdf", "Original relevant fact", 71)])
        first = rag.Ask_question("Explain this fact", 71)
        self.save_chunks(71, [
            self.chunk("a.pdf", "Original relevant fact", 71),
            self.chunk("b.pdf", "Additional relevant detail", 71),
        ])

        second = rag.Ask_question("Explain this fact", 71)

        self.assertEqual(first.answer_mode, "DOCUMENT_SUPPORTED")
        self.assertEqual(second.answer_mode, "DOCUMENT_SUPPORTED")
        self.assertEqual(self.assess.call_count, 2)

    def test_replaced_chunk_content_invalidates_document_answer(self):
        self.save_chunks(71, [self.chunk("a.pdf", "Original evidence", 71)])
        rag.Ask_question("Explain this fact", 71)
        self.save_chunks(71, [self.chunk("a.pdf", "Replaced evidence with a new fact", 71)])

        rag.Ask_question("Explain this fact", 71)

        self.assertEqual(self.assess.call_count, 2)

    def test_new_document_outside_top_five_still_invalidates_old_answer(self):
        chunks = [self.chunk(f"doc-{i}.pdf", f"Relevant passage {i}", 71) for i in range(5)]
        vectors = np.array([[0.1 + i * 0.01, 0.0] for i in range(5)], dtype="float32")
        self.save_chunks(71, chunks, vectors)
        first = rag.Ask_question("Explain this fact", 71)
        chunks.append(self.chunk("unrelated.pdf", "Distant unrelated passage", 71))
        vectors = np.vstack([vectors, np.array([[100.0, 100.0]], dtype="float32")])
        self.save_chunks(71, chunks, vectors)

        second = rag.Ask_question("Explain this fact", 71)

        self.assertEqual(first.answer, second.answer)
        self.assertEqual(self.assess.call_count, 2)

    def test_identical_question_and_context_are_still_user_scoped(self):
        self.save_chunks(71, [self.chunk("one.pdf", "User one passage", 71)])
        self.save_chunks(72, [self.chunk("two.pdf", "User two passage", 72)])
        first = rag.Ask_question("Same question", 71)
        second = rag.Ask_question("Same question", 72)

        self.assertEqual(first.sources[0]["source"], "one.pdf")
        self.assertEqual(second.sources[0]["source"], "two.pdf")
        self.assertEqual(self.assess.call_count, 2)

    def test_cache_query_filters_by_user_even_for_an_identical_cache_key(self):
        result_one = rag.AnswerResult(
            "User one answer", "INSUFFICIENT_CONFIDENCE", None, [], [],
            "LOW", "NONE", "NO_SUFFICIENT_DOCUMENT_EVIDENCE",
        )
        result_two = rag.AnswerResult(
            "User two answer", "INSUFFICIENT_CONFIDENCE", None, [], [],
            "LOW", "NONE", "NO_SUFFICIENT_DOCUMENT_EVIDENCE",
        )
        query_hash, context, pipeline = "same-query-hash", "same-context", "same-pipeline"
        self.assertTrue(answer_cache.Store(71, query_hash, context, pipeline, result_one, 1))
        self.assertTrue(answer_cache.Store(72, query_hash, context, pipeline, result_two, 1))

        first, *_ = answer_cache.Lookup(71, query_hash, context, pipeline, {})
        second, *_ = answer_cache.Lookup(72, query_hash, context, pipeline, {})

        self.assertEqual(first["answer"], "User one answer")
        self.assertEqual(second["answer"], "User two answer")

    def test_legitimate_no_information_result_is_cached(self):
        result = rag.Ask_question("Unanswerable question", 71)
        self.assertEqual(result.answer_mode, "INSUFFICIENT_CONFIDENCE")
        self.assertEqual(result.answer, rag.NO_DOCUMENTS_MESSAGE)
        self.assertEqual(self.cache_count(), 1)

    def test_transient_answer_generation_failure_is_reported_and_not_cached(self):
        self.save_chunks(71, [self.chunk("notes.pdf", "Relevant passage", 71)])
        self.generate.side_effect = RuntimeError("temporary provider failure")

        with self.assertRaises(rag.RAGProcessingError):
            rag.Ask_question("A question", 71)
        self.assertEqual(self.cache_count(), 0)

    def test_ready_documents_without_a_matching_index_bypass_and_do_not_store_cache(self):
        self.ready_document_hashes[71] = {"notes.pdf": "a" * 64}

        result = rag.Ask_question("What does the document say?", 71)

        self.assertEqual(result.answer_mode, "INSUFFICIENT_CONFIDENCE")
        self.assertEqual(self.cache_count(), 0)

    def test_different_pipeline_version_and_expired_entry_are_rejected(self):
        pipeline = answer_cache.Pipeline_fingerprint(rag.generator, 1.0)
        context = answer_cache.Knowledge_base_fingerprint(71, {}, pipeline)
        result = rag.AnswerResult(
            "No information", "INSUFFICIENT_CONFIDENCE", None, [], [],
            "LOW", "NONE", "NO_SUFFICIENT_DOCUMENT_EVIDENCE",
        )
        query_hash = answer_cache.Query_hash("q")
        self.assertTrue(answer_cache.Store(71, query_hash, context, pipeline, result, 1))
        payload, reason, _latency, _calls = answer_cache.Lookup(
            71, query_hash, context, "different-pipeline", {}
        )
        self.assertIsNone(payload)
        self.assertEqual(reason, "miss")

        with self.Session() as session:
            entry = session.scalar(select(AnswerCache))
            entry.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.commit()
        payload, _reason, _latency, _calls = answer_cache.Lookup(
            71, query_hash, context, pipeline, {}
        )
        self.assertIsNone(payload)

    def test_expired_cache_entries_are_removed_during_bounded_cleanup(self):
        result = rag.AnswerResult(
            "No information", "INSUFFICIENT_CONFIDENCE", None, [], [],
            "LOW", "NONE", "NO_SUFFICIENT_DOCUMENT_EVIDENCE",
        )
        pipeline = answer_cache.Pipeline_fingerprint(rag.generator, 1.0)
        context = answer_cache.Knowledge_base_fingerprint(71, {}, pipeline)
        query_hash = answer_cache.Query_hash("old")
        self.assertTrue(answer_cache.Store(71, query_hash, context, pipeline, result, 1))
        with self.Session() as session:
            entry = session.scalar(select(AnswerCache))
            entry.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.commit()
        self.assertTrue(answer_cache.Store(
            71, answer_cache.Query_hash("new"), context, pipeline, result, 1
        ))
        self.assertEqual(self.cache_count(), 1)

    def test_invalid_ttl_disables_cache_but_not_rag(self):
        self.save_chunks(71, [self.chunk("notes.pdf", "Relevant passage", 71)])
        with patch.dict(os.environ, {"ANSWER_CACHE_TTL_SECONDS": "0"}):
            first = rag.Ask_question("A question", 71)
            second = rag.Ask_question("A question", 71)
        self.assertEqual(first.answer_mode, "DOCUMENT_SUPPORTED")
        self.assertEqual(second.answer_mode, "DOCUMENT_SUPPORTED")
        self.assertEqual(self.assess.call_count, 2)

    def test_cache_database_failure_falls_back_to_normal_rag(self):
        self.save_chunks(71, [self.chunk("notes.pdf", "Relevant passage", 71)])
        with patch.object(answer_cache, "SessionLocal", side_effect=RuntimeError("db unavailable")):
            result = rag.Ask_question("A question", 71)
        self.assertEqual(result.answer_mode, "DOCUMENT_SUPPORTED")
        self.assertEqual(self.assess.call_count, 1)

    def test_malformed_cached_data_is_rejected(self):
        pipeline = answer_cache.Pipeline_fingerprint(rag.generator, 1.0)
        context = answer_cache.Knowledge_base_fingerprint(71, {}, pipeline)
        with self.Session() as session:
            session.add(AnswerCache(
                user_id=71, normalized_query_hash=answer_cache.Query_hash("q"),
                answer="Bad data", answer_mode="INSUFFICIENT_CONFIDENCE", message="msg",
                reliability="MODERATE", conflict_status="NONE", fallback_reason="reason",
                claims="malformed", sources=[], context_fingerprint=context,
                pipeline_version=pipeline, gemini_calls=1,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            ))
            session.commit()
        payload, reason, _latency, _calls = answer_cache.Lookup(
            71, answer_cache.Query_hash("q"), context, pipeline, {}
        )
        self.assertIsNone(payload)
        self.assertEqual(reason, "invalid_payload_or_provenance")
        self.assertEqual(self.cache_count(), 0)

    def test_invalid_cached_source_is_rejected_removed_and_regenerated(self):
        self.save_chunks(71, [self.chunk("notes.pdf", "Current source passage", 71)])
        first = rag.Ask_question("What does the source say?", 71)
        with self.Session() as session:
            row = session.scalar(select(AnswerCache))
            changed_sources = [dict(source) for source in row.sources]
            changed_sources[0]["text"] = "stale source text"
            row.sources = changed_sources
            session.commit()

        regenerated = rag.Ask_question("What does the source say?", 71)
        cached_again = rag.Ask_question("What does the source say?", 71)

        self.assertEqual(first.answer_mode, "DOCUMENT_SUPPORTED")
        self.assertEqual(regenerated.answer_mode, "DOCUMENT_SUPPORTED")
        self.assertEqual(regenerated.sources[0]["text"], "Current source passage")
        self.assertEqual(cached_again.answer, regenerated.answer)
        self.assertEqual(self.assess.call_count, 2)

    def test_concurrent_duplicate_inserts_do_not_raise_or_duplicate_rows(self):
        pipeline = answer_cache.Pipeline_fingerprint(rag.generator, 1.0)
        context = answer_cache.Knowledge_base_fingerprint(71, {}, pipeline)
        result = rag.AnswerResult(
            "No information", "INSUFFICIENT_CONFIDENCE", None, [], [],
            "LOW", "NONE", "NO_SUFFICIENT_DOCUMENT_EVIDENCE",
        )
        def store():
            return answer_cache.Store(71, answer_cache.Query_hash("q"), context, pipeline, result, 1)

        with ThreadPoolExecutor(max_workers=4) as pool:
            outcomes = list(pool.map(lambda _index: store(), range(4)))
        self.assertTrue(any(outcomes))
        self.assertEqual(self.cache_count(), 1)

    def test_cached_response_preserves_frontend_response_fields(self):
        self.save_chunks(71, [self.chunk("notes.pdf", "Relevant passage", 71)])
        result = rag.Ask_question("A question", 71)
        response = Query_Ans.model_validate({
            "answer": result.answer, "answer_mode": result.answer_mode,
            "message": result.message, "reliability": result.reliability,
            "conflict_status": result.conflict_status,
            "fallback_reason": result.fallback_reason,
            "claims": result.claims, "sources": result.sources,
        })
        self.assertEqual(response.answer_mode, "DOCUMENT_SUPPORTED")
        self.assertEqual(response.sources[0].source, "notes.pdf")


if __name__ == "__main__":
    unittest.main()
