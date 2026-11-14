import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
CALIBRATION_PATH = Path(__file__).with_name("retrieval_calibration.json")


@dataclass(frozen=True)
class RetrievalChunk:
    document_id: str
    source: str
    page: int | None
    text: str
    user_id: int
    distance: float
    relevant: bool
    metadata: dict[str, Any]

    def as_source(self) -> dict[str, Any]:
        """Keep the existing public source shape; internal score/identity stay private."""
        return {"source": self.source, "page": self.page, "text": self.text}


@dataclass(frozen=True)
class RetrievalResult:
    query: str
    user_id: int
    chunks: tuple[RetrievalChunk, ...]
    evidence_sufficient: bool
    relevance_threshold: float

    @property
    def relevant_chunks(self) -> tuple[RetrievalChunk, ...]:
        return tuple(chunk for chunk in self.chunks if chunk.relevant)

    @property
    def sources(self) -> list[dict[str, Any]]:
        return [chunk.as_source() for chunk in self.relevant_chunks]


def Score_binary_labels(labels: list[bool], predictions: list[bool]) -> dict[str, float | int]:
    true_positive = sum(actual and predicted for actual, predicted in zip(labels, predictions))
    false_positive = sum(not actual and predicted for actual, predicted in zip(labels, predictions))
    false_negative = sum(actual and not predicted for actual, predicted in zip(labels, predictions))
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def Calibrate_distance_threshold(samples: list[tuple[float, bool]]) -> tuple[float, dict[str, float | int]]:
    """Choose the conservative L2 cutoff with the best calibration-set F1."""
    clean_samples = [
        (float(distance), bool(is_relevant))
        for distance, is_relevant in samples
        if math.isfinite(float(distance))
    ]
    labels = [label for _, label in clean_samples]
    if not clean_samples or not any(labels) or all(labels):
        raise ValueError("Calibration requires finite relevant and irrelevant examples")

    distances = sorted({distance for distance, _ in clean_samples})
    candidates = [math.nextafter(distances[0], -math.inf), *distances]
    scored = []
    for threshold in candidates:
        predictions = [distance <= threshold for distance, _ in clean_samples]
        metrics = Score_binary_labels(labels, predictions)
        # Prefer precision, then the smaller (more conservative) cutoff on F1 ties.
        scored.append((metrics["f1"], metrics["precision"], -threshold, threshold, metrics))
    _, _, _, threshold, metrics = max(scored, key=lambda item: item[:3])
    return threshold, metrics


@lru_cache(maxsize=1)
def Get_calibrated_relevance_threshold() -> float:
    try:
        with CALIBRATION_PATH.open("r", encoding="utf-8") as file:
            settings = json.load(file)
        if settings.get("embedding_model") != EMBEDDING_MODEL_NAME:
            raise ValueError("Retrieval calibration does not match the embedding model")
        if settings.get("metric") != "squared_l2":
            raise ValueError("Retrieval calibration does not match the FAISS metric")
        threshold = float(settings["max_squared_l2_distance"])
        if not math.isfinite(threshold) or threshold < 0:
            raise ValueError("Retrieval calibration threshold is invalid")
        return threshold
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError("A valid RAG relevance calibration is required") from error


def Make_retrieval_result(
    query: str,
    user_id: int,
    chunks: list[dict[str, Any]],
    relevance_threshold: float | None = None,
) -> RetrievalResult:
    threshold = (
        Get_calibrated_relevance_threshold()
        if relevance_threshold is None
        else float(relevance_threshold)
    )
    results = []
    for chunk in chunks:
        distance = float(chunk["distance"])
        if not math.isfinite(distance):
            continue
        chunk_user_id = chunk.get("user_id", user_id)
        if chunk_user_id != user_id:
            raise ValueError("Retrieved chunk does not belong to the authenticated user")
        source = str(chunk.get("source", "Unknown"))
        results.append(
            RetrievalChunk(
                document_id=str(chunk.get("document_id", source)),
                source=source,
                page=(
                    int(chunk["page"])
                    if chunk.get("page") is not None
                    else None
                ),
                text=str(chunk["text"]),
                user_id=user_id,
                distance=distance,
                relevant=distance <= threshold,
                metadata={
                    key: value
                    for key, value in chunk.items()
                    if key not in {"text", "distance"}
                },
            )
        )
    relevant = any(chunk.relevant for chunk in results)
    return RetrievalResult(
        query=query,
        user_id=user_id,
        chunks=tuple(results),
        evidence_sufficient=relevant,
        relevance_threshold=threshold,
    )
