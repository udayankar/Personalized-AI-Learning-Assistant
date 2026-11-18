import json
import os
import tempfile
import types
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from Rag import embedder, relevance, answer_cache, vector_store


class GeminiEmbeddingTests(unittest.TestCase):
    def make_provider(self, response=None, side_effect=None):
        client = Mock()
        if side_effect is not None:
            client.models.embed_content.side_effect = side_effect
        else:
            client.models.embed_content.return_value = response
        return embedder.GeminiEmbedder(client=client), client

    def response(self, count=1):
        return types.SimpleNamespace(embeddings=[types.SimpleNamespace(values=[3.0] + [4.0] + [0.0] * 766) for _ in range(count)])

    def test_document_and_query_use_expected_task_types_and_dimensions(self):
        provider, client = self.make_provider(self.response(2))
        document_vectors = provider.embed_documents(["one", "two"])
        self.assertEqual(document_vectors.shape, (2, 768))
        self.assertAlmostEqual(float(np.linalg.norm(document_vectors[0])), 1.0)
        document_config = client.models.embed_content.call_args.kwargs["config"]
        self.assertEqual(document_config.task_type, "RETRIEVAL_DOCUMENT")
        self.assertEqual(document_config.output_dimensionality, 768)

        provider, client = self.make_provider(self.response())
        self.assertEqual(provider.embed_query("question").shape, (768,))
        self.assertEqual(client.models.embed_content.call_args.kwargs["config"].task_type, "RETRIEVAL_QUERY")

        provider, client = self.make_provider(self.response(2))
        query_vectors = provider.embed_queries(["first question", "second question"])
        self.assertEqual(query_vectors.shape, (2, 768))
        self.assertTrue(np.allclose(np.linalg.norm(query_vectors, axis=1), 1.0))
        self.assertEqual(client.models.embed_content.call_args.kwargs["config"].task_type, "RETRIEVAL_QUERY")

    def test_batches_at_configured_limit(self):
        client = Mock()
        client.models.embed_content.side_effect = lambda **kwargs: self.response(len(kwargs["contents"]))
        provider, _ = self.make_provider(side_effect=client.models.embed_content.side_effect)
        provider.client = client
        provider.embed_documents(["text"] * (embedder.MAX_BATCH_SIZE + 1))
        self.assertEqual(client.models.embed_content.call_count, 2)
        self.assertEqual(len(client.models.embed_content.call_args_list[0].kwargs["contents"]), embedder.MAX_BATCH_SIZE)

    def test_invalid_dimensions_nonfinite_and_zero_vectors_are_rejected(self):
        for values in ([0.0] * 768, [float("nan")] + [0.0] * 767, [1.0, 2.0]):
            provider, _client = self.make_provider(types.SimpleNamespace(embeddings=[types.SimpleNamespace(values=values)]))
            with self.subTest(values=values[:2]), self.assertRaises(embedder.EmbeddingProviderError):
                provider.embed_query("question")
        provider, _client = self.make_provider(types.SimpleNamespace(embeddings=[]))
        with self.assertRaises(embedder.EmbeddingProviderError):
            provider.embed_query("question")

    def test_provider_errors_are_not_retried(self):
        transient = RuntimeError("temporary")
        transient.code = 503
        provider, client = self.make_provider(side_effect=[transient] * 4)
        with self.assertRaisesRegex(embedder.EmbeddingProviderError, "request failed"):
            provider.embed_query("question")
        self.assertEqual(client.models.embed_content.call_count, 1)

        permanent = RuntimeError("invalid request")
        permanent.code = 400
        provider, client = self.make_provider(side_effect=permanent)
        with self.assertRaisesRegex(embedder.EmbeddingProviderError, "request failed"):
            provider.embed_query("question")
        self.assertEqual(client.models.embed_content.call_count, 1)

    def test_quota_and_timeout_fail_once_without_repeating_embedding_requests(self):
        quota = RuntimeError("quota")
        quota.code = 429
        quota.response = types.SimpleNamespace(headers={"Retry-After": "3"})
        provider, client = self.make_provider(side_effect=[quota, self.response()])
        with self.assertRaises(embedder.EmbeddingProviderError):
            provider.embed_query("question")
        self.assertEqual(client.models.embed_content.call_count, 1)

        timeout = TimeoutError("network timed out")
        provider, client = self.make_provider(side_effect=[timeout, self.response()])
        with self.assertRaises(embedder.EmbeddingProviderError):
            provider.embed_query("question")
        self.assertEqual(client.models.embed_content.call_count, 1)

    def test_quota_429_without_retry_after_stops_without_repeated_calls(self):
        quota = RuntimeError("quota exhausted")
        quota.code = 429
        provider, client = self.make_provider(side_effect=[quota, self.response()])
        with self.assertRaisesRegex(embedder.EmbeddingProviderError, "request failed"):
            provider.embed_query("question")
        self.assertEqual(client.models.embed_content.call_count, 1)

    def test_startup_does_not_create_client_without_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            provider = embedder.GeminiEmbedder()
            self.assertIsNone(provider.client)
            with self.assertRaisesRegex(embedder.EmbeddingProviderError, "LLM_API_KEY is required"):
                provider.embed_query("question")
            self.assertIsNone(provider.client)

    def test_embedding_client_uses_finite_900_second_timeout_without_sdk_retries(self):
        with patch.dict(os.environ, {"LLM_API_KEY": "unit-test-key"}), \
             patch.object(embedder.genai, "Client") as create_client:
            provider = embedder.GeminiEmbedder()
            provider._get_client()
        http_options = create_client.call_args.kwargs["http_options"]
        self.assertEqual(http_options.timeout, 900_000)
        self.assertEqual(http_options.retry_options.attempts, 1)

    def test_configuration_rejects_unsupported_dimensions(self):
        with patch.dict(os.environ, {"EMBEDDING_DIMENSIONS": "1536"}):
            with self.assertRaisesRegex(ValueError, "must be 768"):
                embedder.get_embedding_configuration()

    def test_minilm_calibration_is_rejected_and_runtime_has_no_faiss_loader(self):
        self.assertFalse(hasattr(vector_store, "faiss"))
        self.assertFalse(hasattr(vector_store, "Load_vector_store"))
        with tempfile.TemporaryDirectory() as directory:
            legacy_minilm = Path(directory) / "retrieval_calibration.json"
            legacy_minilm.write_text(json.dumps({
                "provider": "sentence-transformers",
                "model": "all-MiniLM-L6-v2",
                "embedding_provider": "sentence-transformers",
                "embedding_model": "all-MiniLM-L6-v2",
                "dimensions": 384,
            }), encoding="utf-8")
            with patch.object(relevance, "CALIBRATION_PATH", legacy_minilm):
                relevance.Get_calibrated_relevance_threshold.cache_clear()
                try:
                    with self.assertRaisesRegex(RuntimeError, "valid RAG relevance calibration"):
                        relevance.Get_calibrated_relevance_threshold()
                finally:
                    relevance.Get_calibrated_relevance_threshold.cache_clear()

    def test_cache_fingerprint_changes_with_embedding_configuration(self):
        original = embedder.get_embedding_configuration()
        baseline = answer_cache.Pipeline_fingerprint(types.SimpleNamespace(MODEL_NAME="generator"), 0.5)
        alternate = replace(original, dimensions=1536)
        with patch.object(answer_cache, "get_embedding_configuration", return_value=alternate):
            changed = answer_cache.Pipeline_fingerprint(types.SimpleNamespace(MODEL_NAME="generator"), 0.5)
        self.assertNotEqual(baseline, changed)

    def test_cache_fingerprint_changes_with_chunking_configuration(self):
        baseline = answer_cache.Pipeline_fingerprint(types.SimpleNamespace(MODEL_NAME="generator"), 0.5)
        original = answer_cache.get_chunking_configuration()
        changed_config = {**original, "chunk_size": original["chunk_size"] + 1}
        with patch.object(answer_cache, "get_chunking_configuration", return_value=changed_config):
            changed = answer_cache.Pipeline_fingerprint(types.SimpleNamespace(MODEL_NAME="generator"), 0.5)
        self.assertNotEqual(baseline, changed)


if __name__ == "__main__":
    unittest.main()
