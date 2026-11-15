import importlib
import json
import sys
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import numpy as np


# Avoid loading model weights or contacting model providers in storage/isolation tests.
for _module_name in (
    "Rag.rag",
    "Rag.ingest",
    "Rag.embedder",
    "Rag.generator",
    "Rag.vector_store",
    "Rag.document_tracker",
    "Rag.user_storage",
):
    sys.modules.pop(_module_name, None)

sentence_transformers_stub = types.ModuleType("sentence_transformers")
sentence_transformers_stub.SentenceTransformer = lambda *_args, **_kwargs: Mock()
generator_stub = types.ModuleType("Rag.generator")
generator_stub.Assess_document_evidence = Mock(return_value={
    "coverage_status": "COMPLETE",
    "required_facts": [{"fact_id": "F1", "description": "Relevant fact", "reference_ids": ["R1"]}],
    "missing_facts": [], "relationships": [],
})
generator_stub.Generate_claims = Mock(return_value={
    "claims": [{"claim_id": "C1", "text": "Test answer", "citation_ids": ["R1"]}],
})
generator_stub.Verify_document_claims = Mock(side_effect=lambda _question, claims, _passages: {
    "claim_results": [{
        "claim_id": claim["claim_id"], "classification": "SUPPORTED",
        "citation_ids": claim["citation_ids"], "qualified_text": None,
    } for claim in claims],
    "relationships": [],
})
generator_stub.Generate_general_answer = Mock(return_value={
    "answer": "General test answer", "can_answer": True,
})
with patch.dict(
    sys.modules,
    {
        "sentence_transformers": sentence_transformers_stub,
        "Rag.generator": generator_stub,
    },
):
    ingest = importlib.import_module("Rag.ingest")
    rag = importlib.import_module("Rag.rag")
    vector_store = importlib.import_module("Rag.vector_store")
    user_storage = importlib.import_module("Rag.user_storage")
    document_tracker = importlib.import_module("Rag.document_tracker")
    relevance = importlib.import_module("Rag.relevance")


class RagUserIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.documents_root_patch = patch.object(
            user_storage, "DOCUMENTS_ROOT", root / "documents"
        )
        self.storage_root_patch = patch.object(
            user_storage, "STORAGE_ROOT", root / "storage"
        )
        self.documents_root_patch.start()
        self.storage_root_patch.start()
        self.addCleanup(self.documents_root_patch.stop)
        self.addCleanup(self.storage_root_patch.stop)
        self.addCleanup(self.temp_dir.cleanup)
        self.cache_lookup_patch = patch.object(
            rag.answer_cache, "Lookup", return_value=(None, "miss", 0.0, 0)
        )
        self.cache_lookup_patch.start()
        self.addCleanup(self.cache_lookup_patch.stop)
        self.cache_store_patch = patch.object(rag.answer_cache, "Store", return_value=False)
        self.cache_store_patch.start()
        self.addCleanup(self.cache_store_patch.stop)

    def _write_document(self, user_id, filename, contents):
        documents_dir, _ = user_storage.Get_user_paths(user_id)
        documents_dir.mkdir(parents=True, exist_ok=True)
        (documents_dir / filename).write_bytes(contents)

    def _mock_process(self, path, user_id):
        user_name = path.parent.name
        vector = np.array([[1.0, 0.0]], dtype="float32") if user_name == "user_101" else np.array([[0.0, 1.0]], dtype="float32")
        return ([{
            "source": path.name,
            "document_id": path.name,
            "user_id": user_id,
            "page": 1,
            "text": user_name,
        }], vector)

    def test_storage_paths_require_positive_integer_database_identity(self):
        for invalid_id in (None, True, 0, -1, "../user_8", "7"):
            with self.subTest(user_id=invalid_id):
                with self.assertRaises(ValueError):
                    user_storage.Get_user_paths(invalid_id)

        documents_dir, storage_dir = user_storage.Get_user_paths(101)
        self.assertEqual(documents_dir.name, "user_101")
        self.assertEqual(storage_dir.name, "user_101")
        self.assertEqual(documents_dir.parent, user_storage.DOCUMENTS_ROOT)
        self.assertEqual(storage_dir.parent, user_storage.STORAGE_ROOT)

    def test_users_can_retrieve_only_their_own_documents(self):
        self._write_document(101, "same-name.pdf", b"user 101 document")
        self._write_document(202, "same-name.PDF", b"user 202 document")
        with patch.object(ingest, "Process_document", side_effect=self._mock_process):
            ingest.Build_rag(101)
            ingest.Build_rag(202)

        rag.model = types.SimpleNamespace(
            encode=lambda query: np.array([1.0, 0.0]) if "A" in query else np.array([0.0, 1.0])
        )
        rag.Generate_claims = Mock(return_value={
            "claims": [{"claim_id": "C1", "text": "Answer", "citation_ids": ["R1"]}],
        })
        answer_a, sources_a = rag.Ask_question("question for A", 101)
        answer_b, sources_b = rag.Ask_question("question for B", 202)

        self.assertEqual(answer_a, "Answer")
        self.assertEqual(answer_b, "Answer")
        self.assertEqual([source["text"] for source in sources_a], ["user_101"])
        self.assertEqual([source["text"] for source in sources_b], ["user_202"])
        self.assertEqual(sources_a[0]["source"], "same-name.pdf")
        self.assertEqual(sources_b[0]["source"], "same-name.PDF")

    def test_empty_knowledge_base_returns_empty_sources_without_loading_other_users(self):
        result = rag.Ask_question("question", 303)

        self.assertEqual(result.answer_mode, rag.GENERAL_KNOWLEDGE)
        self.assertEqual(result.sources, [])

    def test_index_and_chunks_reload_from_the_same_users_directory(self):
        self._write_document(101, "a.pdf", b"owner A")
        self._write_document(202, "b.pdf", b"owner B")
        with patch.object(ingest, "Process_document", side_effect=self._mock_process):
            ingest.Build_rag(101)
            ingest.Build_rag(202)

        index_a, chunks_a = vector_store.Load_vector_store(101)
        index_b, chunks_b = vector_store.Load_vector_store(202)
        self.assertEqual(index_a.ntotal, 1)
        self.assertEqual(index_b.ntotal, 1)
        self.assertEqual(chunks_a[0]["text"], "user_101")
        self.assertEqual(chunks_b[0]["text"], "user_202")

    def test_concurrent_ingestion_writes_independent_user_indexes(self):
        self._write_document(101, "a.pdf", b"owner A")
        self._write_document(202, "b.pdf", b"owner B")
        with patch.object(ingest, "Process_document", side_effect=self._mock_process):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(ingest.Build_rag, user_id) for user_id in (101, 202)]
                [future.result(timeout=5) for future in futures]

        _, chunks_a = vector_store.Load_vector_store(101)
        _, chunks_b = vector_store.Load_vector_store(202)
        self.assertEqual(chunks_a[0]["text"], "user_101")
        self.assertEqual(chunks_b[0]["text"], "user_202")

    def test_metadata_is_scoped_by_user_even_for_identical_filenames(self):
        self._write_document(101, "notes.pdf", b"A version")
        self._write_document(202, "notes.pdf", b"B version")

        status_a, hash_a = document_tracker.Document_status(
            user_storage.Get_user_paths(101)[0] / "notes.pdf", 101
        )
        status_b, hash_b = document_tracker.Document_status(
            user_storage.Get_user_paths(202)[0] / "notes.pdf", 202
        )
        self.assertEqual((status_a, status_b), ("new", "new"))
        self.assertNotEqual(hash_a, hash_b)

        document_tracker.Save_document_metadata({"notes.pdf": hash_a}, 101)
        self.assertEqual(document_tracker.Load_document_metadata(202), {})

    def test_retrieval_handles_empty_one_result_and_invalid_faiss_indices(self):
        self.assertEqual(vector_store.Search(None, [0.0, 1.0], k=5)[1].size, 0)
        empty_index = vector_store.faiss.IndexFlatL2(2)
        self.assertEqual(vector_store.Create_vector_store([]), None)
        self.assertEqual(vector_store.Search(empty_index, [0.0, 1.0], k=5)[1].size, 0)
        empty_result = vector_store.Retrieve("q", empty_index, [], Mock(), 101, k=5)
        self.assertEqual(empty_result.chunks, ())
        self.assertFalse(empty_result.evidence_sufficient)
        self.assertEqual(vector_store.Retrieve("q", None, [], Mock(), 101, k=5).chunks, ())

        index = vector_store.Create_vector_store(np.array([[1.0, 0.0]], dtype="float32"))
        model = types.SimpleNamespace(encode=lambda _query: np.array([1.0, 0.0]))
        chunks = [{"page": 1, "text": "only result", "source": "one.pdf", "user_id": 101}]
        results = vector_store.Retrieve("q", index, chunks, model, 101, k=5)
        self.assertEqual(len(results.chunks), 1)
        self.assertEqual(results.chunks[0].source, "one.pdf")
        self.assertTrue(results.evidence_sufficient)
        self.assertEqual(results.chunks[0].page, 1)
        self.assertEqual(results.chunks[0].user_id, 101)
        self.assertEqual(results.chunks[0].distance, 0.0)
        self.assertEqual(results.sources, [{"source": "one.pdf", "page": 1, "text": "only result"}])

        with patch.object(
            vector_store,
            "Search",
            return_value=(np.array([0.0]), np.array([-1])),
        ):
            result = vector_store.Retrieve("q", index, chunks, model, 101)
            self.assertEqual(result.chunks, ())
            self.assertFalse(result.evidence_sufficient)

    def test_relevance_assessment_filters_irrelevant_and_keeps_mixed_results_internal(self):
        vectors = np.array([[0.1, 0.0], [5.0, 5.0]], dtype="float32")
        index = vector_store.Create_vector_store(vectors)
        model = types.SimpleNamespace(encode=lambda _query: np.array([0.0, 0.0]))
        chunks = [
            {"page": 2, "text": "relevant text", "source": "a.pdf", "document_id": "doc-a", "user_id": 101},
            {"page": 9, "text": "unrelated text", "source": "b.pdf", "document_id": "doc-b", "user_id": 101},
        ]

        result = vector_store.Retrieve("q", index, chunks, model, 101)

        self.assertTrue(result.evidence_sufficient)
        self.assertEqual([chunk.relevant for chunk in result.chunks], [True, False])
        self.assertAlmostEqual(result.chunks[0].distance, 0.01, places=6)
        self.assertEqual(result.chunks[1].distance, 50.0)
        self.assertEqual([chunk.document_id for chunk in result.relevant_chunks], ["doc-a"])
        self.assertEqual(result.relevant_chunks[0].metadata["user_id"], 101)
        self.assertEqual(result.relevant_chunks[0].page, 2)
        self.assertEqual(result.sources, [{"source": "a.pdf", "page": 2, "text": "relevant text"}])

    def test_irrelevant_and_multiple_document_results_are_assessed(self):
        model = types.SimpleNamespace(encode=lambda _query: np.array([0.0, 0.0]))
        irrelevant_index = vector_store.Create_vector_store(np.array([[8.0, 8.0]], dtype="float32"))
        irrelevant = vector_store.Retrieve(
            "unrelated question",
            irrelevant_index,
            [{"page": 1, "text": "unrelated", "source": "unrelated.pdf", "user_id": 101}],
            model,
            101,
        )
        self.assertFalse(irrelevant.evidence_sufficient)
        self.assertEqual(irrelevant.sources, [])

        multi_index = vector_store.Create_vector_store(
            np.array([[0.1, 0.0], [0.2, 0.0]], dtype="float32")
        )
        multi = vector_store.Retrieve(
            "question requiring two documents",
            multi_index,
            [
                {"page": 1, "text": "part one", "source": "first.pdf", "user_id": 101},
                {"page": 4, "text": "part two", "source": "second.pdf", "user_id": 101},
            ],
            model,
            101,
        )
        self.assertTrue(multi.evidence_sufficient)
        self.assertEqual([chunk.source for chunk in multi.relevant_chunks], ["first.pdf", "second.pdf"])
        self.assertEqual([chunk.page for chunk in multi.relevant_chunks], [1, 4])

    def test_retrieval_rejects_chunks_from_a_different_user(self):
        index = vector_store.Create_vector_store(np.array([[0.0, 0.0]], dtype="float32"))
        model = types.SimpleNamespace(encode=lambda _query: np.array([0.0, 0.0]))
        with self.assertRaises(ValueError):
            vector_store.Retrieve(
                "q", index,
                [{"page": 1, "text": "foreign", "source": "foreign.pdf", "user_id": 202}],
                model, 101,
            )

    def test_missing_store_is_empty_but_partial_store_fails_closed(self):
        self.assertEqual(vector_store.Load_vector_store(404), (None, []))

        _, storage_dir = user_storage.Get_user_paths(404)
        storage_dir.mkdir(parents=True, exist_ok=True)
        (storage_dir / "chunks.pkl").write_bytes(b"partial")
        with self.assertRaises(FileNotFoundError):
            vector_store.Load_vector_store(404)

    def test_corrupt_index_and_chunk_files_fail_closed(self):
        _, storage_dir = user_storage.Get_user_paths(405)
        storage_dir.mkdir(parents=True, exist_ok=True)
        (storage_dir / "index.faiss").write_bytes(b"not a FAISS index")
        (storage_dir / "chunks.pkl").write_bytes(b"not a pickle")
        with self.assertRaises(ValueError):
            vector_store.Load_vector_store(405)

        _, storage_dir = user_storage.Get_user_paths(406)
        storage_dir.mkdir(parents=True, exist_ok=True)
        valid_index = vector_store.Create_vector_store(np.array([[0.0, 0.0]], dtype="float32"))
        vector_store.faiss.write_index(valid_index, str(storage_dir / "index.faiss"))
        (storage_dir / "chunks.pkl").write_bytes(b"not a pickle")
        with self.assertRaises(ValueError):
            vector_store.Load_vector_store(406)

    def test_evaluation_dataset_and_calibrated_cutoff_are_explicit(self):
        fixture = Path(__file__).parent / "fixtures" / "rag_evaluation.json"
        dataset = json.loads(fixture.read_text(encoding="utf-8"))
        self.assertEqual(len(dataset["cases"]), 40)
        self.assertEqual(sum(case["split"] == "calibration" for case in dataset["cases"]), 28)
        self.assertEqual(sum(case["split"] == "validation" for case in dataset["cases"]), 12)
        categories = {case["category"] for case in dataset["cases"]}
        self.assertTrue({"answerable", "unanswerable", "irrelevant", "multi_document", "ambiguous", "conflicting", "empty_knowledge_base"}.issubset(categories))
        for case in dataset["cases"]:
            self.assertIn("expected_answer_points", case)
            self.assertIn("evidence_sufficient", case)
            self.assertIn("expected_supporting_passage_ids", case)
            self.assertIn("expected_answer_mode", case)

        threshold = relevance.Get_calibrated_relevance_threshold()
        self.assertGreater(threshold, 0)
        self.assertAlmostEqual(threshold, 0.942206859588623)

    def test_threshold_calibration_uses_labeled_distance_examples(self):
        threshold, metrics = relevance.Calibrate_distance_threshold([
            (0.1, True), (0.2, True), (0.5, False), (0.8, False)
        ])
        self.assertEqual(threshold, 0.2)
        self.assertEqual(metrics["precision"], 1.0)
        self.assertEqual(metrics["recall"], 1.0)

    def test_legacy_shared_paths_are_not_part_of_any_user_store(self):
        documents_dir, storage_dir = user_storage.Get_user_paths(101)
        self.assertEqual(documents_dir.name, "user_101")
        self.assertEqual(storage_dir.name, "user_101")
        self.assertEqual(documents_dir.parent, user_storage.DOCUMENTS_ROOT)
        self.assertEqual(storage_dir.parent, user_storage.STORAGE_ROOT)
        self.assertNotEqual(documents_dir, Path("Data/Documents"))
        self.assertNotEqual(storage_dir, Path("Storage"))

    def test_insufficient_evidence_does_not_call_answer_generator(self):
        index = vector_store.Create_vector_store(np.array([[8.0, 8.0]], dtype="float32"))
        chunks = [{
            "page": 1,
            "text": "Unrelated passage",
            "source": "unrelated.pdf",
            "document_id": "unrelated-doc",
            "user_id": 101,
        }]
        vector_store.Save_vector_store(index, chunks, 101)
        rag.model = types.SimpleNamespace(encode=lambda _query: np.array([0.0, 0.0]))
        generator = Mock(return_value={
            "claims": [{"claim_id": "C1", "text": "Should not be generated", "citation_ids": ["R1"]}],
        })
        rag.Generate_claims = generator
        rag.Generate_general_answer = Mock(return_value={
            "answer": "General answer", "can_answer": True,
        })

        result = rag.Ask_question("unrelated question", 101)

        self.assertEqual(result.answer_mode, rag.GENERAL_KNOWLEDGE)
        self.assertEqual(result.sources, [])
        generator.assert_not_called()


if __name__ == "__main__":
    unittest.main()
