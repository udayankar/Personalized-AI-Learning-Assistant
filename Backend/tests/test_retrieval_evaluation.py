import json
import math
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from Rag import chunker, embedder, relevance
from Rag.embedder import EmbeddingProviderError
from scripts import evaluate_rag


class GeminiRetrievalEvaluationTests(unittest.TestCase):
    def test_dataset_has_disjoint_passages_and_at_least_one_hundred_cases(self):
        dataset = evaluate_rag.load_dataset()
        self.assertEqual({name: len(split["cases"]) for name, split in dataset["splits"].items()}, {
            "calibration": 40, "validation": 40, "holdout": 40,
        })
        passage_ids = [p["id"] for split in dataset["splits"].values() for p in split["passages"]]
        self.assertEqual(len(passage_ids), len(set(passage_ids)))
        split_sources = [
            {p["source"] for p in split["passages"]}
            for split in dataset["splits"].values()
        ]
        self.assertFalse(split_sources[0] & split_sources[1])
        self.assertFalse(split_sources[0] & split_sources[2])
        self.assertFalse(split_sources[1] & split_sources[2])
        requested_categories = {
            "direct_factual", "multi_passage", "similar_terminology", "paraphrased",
            "buried_detail", "ambiguous", "absent_answer", "irrelevant",
            "lexical_distractor", "technical_precision",
        }
        for name in ("validation", "holdout"):
            self.assertTrue(requested_categories.issubset({
                case["category"] for case in dataset["splits"][name]["cases"]
            }))
        self.assertEqual(len(dataset["sha256"]), 64)

    def test_dry_run_reports_request_count_without_embedding(self):
        dataset = evaluate_rag.load_dataset()
        with TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "eval-cache.json"
            with patch.object(evaluate_rag.embedding_provider, "embed_documents", side_effect=AssertionError("API called")), \
                 patch.object(evaluate_rag.embedding_provider, "embed_queries", side_effect=AssertionError("API called")):
                output = evaluate_rag.evaluate(dataset, cache_path=cache_path, execute=False)
        usage = output["usage"]
        self.assertEqual(usage["uncached_document_inputs"], 80)
        self.assertEqual(usage["uncached_query_inputs"], 120)
        self.assertEqual(usage["estimated_api_requests"], 3)
        self.assertLessEqual(usage["estimated_api_requests"], 4)
        self.assertEqual(usage["generation_requests"], 0)
        self.assertFalse(cache_path.exists())

    def test_ranking_metrics_use_expected_relevance_and_top_k(self):
        cases = [
            {"id": "q1", "category": "direct", "expected_relevant_passage_ids": ["A"], "answer_present": True},
            {"id": "q2", "category": "absent", "expected_relevant_passage_ids": [], "answer_present": False},
        ]
        ranked = {
            "q1": [{"passage_id": "B", "distance": .1}, {"passage_id": "A", "distance": .2}, {"passage_id": "C", "distance": .3}],
            "q2": [{"passage_id": "D", "distance": .1}, {"passage_id": "E", "distance": .2}, {"passage_id": "F", "distance": .3}],
        }
        metrics = evaluate_rag._ranking_metrics(cases, ranked)["overall"]["3"]
        self.assertEqual(metrics["answerable_cases"], 1)
        self.assertEqual(metrics["recall"], 1.0)
        self.assertAlmostEqual(metrics["precision"], 1 / 6)
        self.assertAlmostEqual(metrics["mrr"], 0.25)
        self.assertAlmostEqual(metrics["ndcg"], 0.5 / math.log2(3))

    def test_threshold_policy_limits_false_positives_and_reports_no_answer(self):
        cases = [
            {"id": "positive", "expected_relevant_passage_ids": ["A"], "answer_present": True},
            {"id": "negative", "expected_relevant_passage_ids": [], "answer_present": False},
        ]
        ranked = {
            "positive": [{"passage_id": "A", "distance": .2}, {"passage_id": "B", "distance": .8}],
            "negative": [{"passage_id": "C", "distance": .6}, {"passage_id": "D", "distance": .9}],
        }
        threshold, metrics = evaluate_rag._calibrate(cases, ranked)
        self.assertEqual(threshold, .2)
        self.assertEqual(metrics["false_positive_rate"], 0.0)
        self.assertEqual(metrics["false_negative_rate"], 0.0)
        self.assertEqual(metrics["no_answer_rejection_rate"], 1.0)
        self.assertEqual(relevance.Make_retrieval_result("q", 1, [{
            "source": "doc", "page": 1, "text": "edge", "distance": threshold,
        }], threshold).relevant_chunks[0].distance, threshold)

    def test_live_request_wrapper_hard_stops_at_explicit_bounded_attempt_budget(self):
        class Models:
            def __init__(self):
                self.calls = 0
            def embed_content(self, **_kwargs):
                self.calls += 1
                return self.calls
        client = SimpleNamespace(models=Models())
        budget = {"calls": 0, "limit": 7}
        wrapped = evaluate_rag._BudgetedClient(client, budget)
        self.assertIs(wrapped._client, client)
        for _ in range(budget["limit"]):
            wrapped.models.embed_content(contents=[])
        self.assertEqual(budget["calls"], budget["limit"])
        self.assertEqual(client.models.calls, budget["limit"])
        with self.assertRaises(EmbeddingProviderError):
            wrapped.models.embed_content(contents=[])
        self.assertEqual(client.models.calls, budget["limit"])

    def test_embedding_failure_reports_attempt_count_and_restores_provider_client(self):
        class Models:
            def embed_content(self, **_kwargs):
                return None
        class Provider:
            client = "original"
            def _get_client(self):
                return SimpleNamespace(models=Models())
            def embed_documents(self, _texts):
                self.client.models.embed_content(contents=[])
                raise RuntimeError("simulated provider failure")
        provider = Provider()
        with TemporaryDirectory() as temp_dir:
            with self.assertRaises(evaluate_rag.EvaluationEmbeddingError) as raised:
                evaluate_rag.embed_with_cache(
                    evaluate_rag.load_dataset(), Path(temp_dir) / "cache.json", provider=provider,
                )
        self.assertEqual(raised.exception.request_attempts, 1)
        self.assertEqual(raised.exception.cause_type, "RuntimeError")
        self.assertEqual(provider.client, "original")

    def test_calibration_artifact_accepts_matching_full_configuration(self):
        config = embedder.get_embedding_configuration()
        artifact = {
            **config.as_dict(),
            "embedding_provider": config.provider,
            "embedding_model": config.model,
            "dimensions": config.dimensions,
            "metric": config.distance_metric,
            "distance_convention": "euclidean_l2_unsquared",
            "chunking": chunker.get_chunking_configuration(),
            "retrieval_top_k": 5,
            "dataset_version": relevance.CALIBRATION_DATASET_VERSION,
            "dataset_sha256": "a" * 64,
            "calibrated_at_utc": "2026-01-01T00:00:00+00:00",
            "calibration_status": "calibrated",
            "calibration_metrics": {"precision": 1.0},
            "validation_metrics": {"precision": 1.0},
            "max_distance": .75,
            "threshold_comparison": "<=",
        }
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "calibration.json"
            path.write_text(json.dumps(artifact), encoding="utf-8")
            with patch.object(relevance, "CALIBRATION_PATH", path):
                relevance.Get_calibrated_relevance_threshold.cache_clear()
                self.assertEqual(relevance.Get_calibrated_relevance_threshold(), .75)
                relevance.Get_calibrated_relevance_threshold.cache_clear()

    def test_calibration_rejects_configuration_or_artifact_mismatches(self):
        config = embedder.get_embedding_configuration()
        base = {
            **config.as_dict(), "embedding_provider": config.provider,
            "embedding_model": config.model, "dimensions": config.dimensions,
            "metric": config.distance_metric, "distance_convention": "euclidean_l2_unsquared",
            "chunking": chunker.get_chunking_configuration(), "retrieval_top_k": 5,
            "dataset_version": relevance.CALIBRATION_DATASET_VERSION, "dataset_sha256": "b" * 64,
            "calibrated_at_utc": "2026-01-01T00:00:00+00:00",
            "calibration_status": "calibrated", "calibration_metrics": {"precision": 1.0},
            "validation_metrics": {"precision": 1.0}, "max_distance": .5, "threshold_comparison": "<=",
        }
        mutations = {
            "embedding_provider": "sentence-transformers",
            "embedding_model": "wrong-model",
            "dimensions": 384,
            "document_task_type": "SEMANTIC_SIMILARITY",
            "query_task_type": "RETRIEVAL_DOCUMENT",
            "normalization": "none",
            "metric": "squared_l2",
            "distance_convention": "squared_l2",
            "chunking": {**chunker.get_chunking_configuration(), "chunk_size": 10},
            "retrieval_top_k": 10,
            "dataset_sha256": "bad-hash",
            "dataset_version": "unrecognized-dataset-v0",
            "threshold_comparison": "<",
        }
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "calibration.json"
            for key, value in mutations.items():
                artifact = {**base, key: value}
                path.write_text(json.dumps(artifact), encoding="utf-8")
                with patch.object(relevance, "CALIBRATION_PATH", path):
                    relevance.Get_calibrated_relevance_threshold.cache_clear()
                    with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, "valid RAG relevance calibration"):
                        relevance.Get_calibrated_relevance_threshold()
            path.write_text("{not-json", encoding="utf-8")
            with patch.object(relevance, "CALIBRATION_PATH", path):
                relevance.Get_calibrated_relevance_threshold.cache_clear()
                with self.assertRaises(RuntimeError):
                    relevance.Get_calibrated_relevance_threshold()
            relevance.Get_calibrated_relevance_threshold.cache_clear()

    def test_calibration_rejects_nonfinite_metrics_and_invalid_thresholds(self):
        config = embedder.get_embedding_configuration()
        base = {
            **config.as_dict(), "embedding_provider": config.provider,
            "embedding_model": config.model, "dimensions": config.dimensions,
            "metric": config.distance_metric, "distance_convention": "euclidean_l2_unsquared",
            "chunking": chunker.get_chunking_configuration(), "retrieval_top_k": 5,
            "dataset_version": relevance.CALIBRATION_DATASET_VERSION, "dataset_sha256": "c" * 64,
            "calibrated_at_utc": "2026-01-01T00:00:00+00:00",
            "calibration_status": "calibrated", "calibration_metrics": {"precision": 1.0},
            "validation_metrics": {"precision": 1.0}, "max_distance": .5, "threshold_comparison": "<=",
        }
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "calibration.json"
            for key, value in (("max_distance", float("nan")), ("max_distance", -0.1),
                               ("max_distance", True),
                               ("validation_metrics", {"precision": float("inf")})):
                path.write_text(json.dumps({**base, key: value}), encoding="utf-8")
                with patch.object(relevance, "CALIBRATION_PATH", path):
                    relevance.Get_calibrated_relevance_threshold.cache_clear()
                    with self.assertRaises(relevance.CalibrationError):
                        relevance.Get_calibrated_relevance_threshold()
            relevance.Get_calibrated_relevance_threshold.cache_clear()

    def test_missing_calibration_error_names_expected_path(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "missing.json"
            with patch.object(relevance, "CALIBRATION_PATH", path):
                relevance.Get_calibrated_relevance_threshold.cache_clear()
                with self.assertRaises(relevance.CalibrationError) as raised:
                    relevance.Get_calibrated_relevance_threshold()
                self.assertIn(str(path), str(raised.exception))
                relevance.Get_calibrated_relevance_threshold.cache_clear()


if __name__ == "__main__":
    unittest.main()
