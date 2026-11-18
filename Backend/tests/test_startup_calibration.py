import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from App import main
from Rag import relevance


class RetrievalCalibrationStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_startup_does_not_require_or_load_retrieval_calibration(self):
        with tempfile.TemporaryDirectory() as directory:
            missing_path = Path(directory) / "missing-calibration.json"
            with patch.object(relevance, "CALIBRATION_PATH", missing_path), \
                 patch.object(main, "recover_interrupted_document_work") as recovery, \
                 patch.object(relevance, "Get_calibrated_relevance_threshold") as calibration:
                async with main.lifespan(main.app):
                    recovery.assert_called_once_with()
                calibration.assert_not_called()


if __name__ == "__main__":
    unittest.main()
