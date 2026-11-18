import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from App import main
from Rag import chunker, relevance
from Rag.embedder import get_embedding_configuration


def valid_artifact():
    config = get_embedding_configuration()
    return {
        **config.as_dict(),
        "embedding_provider": config.provider,
        "embedding_model": config.model,
        "dimensions": config.dimensions,
        "metric": config.distance_metric,
        "distance_convention": relevance.DISTANCE_CONVENTION,
        "chunking": chunker.get_chunking_configuration(),
        "retrieval_top_k": relevance.RETRIEVAL_TOP_K,
        "dataset_version": relevance.CALIBRATION_DATASET_VERSION,
        "dataset_sha256": "a" * 64,
        "calibrated_at_utc": "2026-01-01T00:00:00+00:00",
        "calibration_status": "calibrated",
        "calibration_metrics": {"precision": 1.0},
        "validation_metrics": {"precision": 1.0},
        "max_distance": 0.5,
        "threshold_comparison": "<=",
    }


class CalibrationStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_startup_accepts_valid_calibration_without_provider_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calibration.json"
            path.write_text(json.dumps(valid_artifact()), encoding="utf-8")
            with patch.object(relevance, "CALIBRATION_PATH", path), \
                 patch.object(main, "recover_interrupted_document_work") as recovery:
                relevance.Get_calibrated_relevance_threshold.cache_clear()
                try:
                    async with main.lifespan(main.app):
                        self.assertEqual(relevance.Get_calibrated_relevance_threshold(), 0.5)
                    recovery.assert_called_once_with()
                finally:
                    relevance.Get_calibrated_relevance_threshold.cache_clear()

    async def test_startup_fails_before_recovery_when_calibration_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing-calibration.json"
            with patch.object(relevance, "CALIBRATION_PATH", path), \
                 patch.object(main, "recover_interrupted_document_work") as recovery:
                relevance.Get_calibrated_relevance_threshold.cache_clear()
                try:
                    with self.assertRaises(relevance.CalibrationError):
                        async with main.lifespan(main.app):
                            self.fail("Startup must not continue without calibration")
                    recovery.assert_not_called()
                finally:
                    relevance.Get_calibrated_relevance_threshold.cache_clear()


if __name__ == "__main__":
    unittest.main()
