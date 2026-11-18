"""Gemini retrieval calibration/evaluation; dry-run unless --execute is supplied."""
import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env", override=False)
sys.path.insert(0, str(BACKEND_DIR))

from Rag import chunker, relevance
from Rag.embedder import (
    MAX_BATCH_SIZE,
    MAX_ATTEMPTS,
    EmbeddingProviderError,
    embedding_provider,
    get_embedding_configuration,
)

LEGACY_DATASET_PATH = BACKEND_DIR / "tests" / "fixtures" / "rag_evaluation.json"
ADDITIONS_PATH = BACKEND_DIR / "tests" / "fixtures" / "rag_retrieval_evaluation_additions.json"
CALIBRATION_PATH = BACKEND_DIR / "Rag" / "retrieval_calibration.gemini.json"
CACHE_PATH = BACKEND_DIR / ".cache" / "retrieval-evaluation" / "embeddings.json"
TOP_K_VALUES = (1, 3, 5)
FALSE_POSITIVE_RATE_CEILING = 0.05


class EvaluationEmbeddingError(RuntimeError):
    def __init__(self, usage, request_attempts, cause_type):
        super().__init__(f"Embedding evaluation failed ({cause_type})")
        self.usage = usage
        self.request_attempts = request_attempts
        self.cause_type = cause_type


def _canonical_hash(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_dataset():
    legacy = json.loads(LEGACY_DATASET_PATH.read_text(encoding="utf-8"))
    additions = json.loads(ADDITIONS_PATH.read_text(encoding="utf-8"))
    calibration_passages = [
        {
            "id": passage["id"], "source": document["source"], "text": passage["text"],
        }
        for document in legacy["documents"]
        for page in document["pages"]
        for passage in page["passages"]
    ] + additions["calibration_passages"]
    calibration_cases = [
        {
            "id": case["id"],
            "category": _legacy_category(case["category"]),
            "question": case["question"],
            "expected_relevant_passage_ids": case["expected_supporting_passage_ids"],
            "answer_present": bool(case["evidence_sufficient"]),
            "expected_behavior": "retrieve labeled supporting passages" if case["evidence_sufficient"]
            else "reject unsupported evidence",
        }
        for case in legacy["cases"] if case["split"] == "calibration"
    ] + additions["calibration_cases"]
    dataset = {
        "version": additions["version"],
        "description": additions["description"],
        "splits": {
            "calibration": {"passages": calibration_passages, "cases": calibration_cases},
            "validation": {"passages": additions["validation_passages"], "cases": additions["validation_cases"]},
            "holdout": {"passages": additions["holdout_passages"], "cases": additions["holdout_cases"]},
        },
    }
    dataset["sha256"] = _canonical_hash(dataset)
    _validate_dataset(dataset)
    return dataset


def _legacy_category(category):
    return {
        "answerable": "direct_factual",
        "exact_terminology": "technical_precision",
        "multi_document": "multi_passage",
        "unanswerable": "absent_answer",
    }.get(category, category)


def _validate_dataset(dataset):
    all_cases = []
    sources_by_split = {}
    all_passage_ids = set()
    all_case_ids = set()
    all_questions = set()
    for split_name, split in dataset["splits"].items():
        passages = split["passages"]
        passage_ids = {item["id"] for item in passages}
        if len(passage_ids) != len(passages) or all_passage_ids.intersection(passage_ids):
            raise ValueError("Evaluation passage IDs must be unique across splits")
        sources = {item["source"] for item in passages}
        if any(sources.intersection(previous) for previous in sources_by_split.values()):
            raise ValueError("Evaluation source documents must not cross splits")
        sources_by_split[split_name] = sources
        all_passage_ids.update(passage_ids)
        for case in split["cases"]:
            normalized_question = " ".join(case["question"].split()).casefold()
            if (
                case["id"] in all_case_ids or not normalized_question
                or normalized_question in all_questions
            ):
                raise ValueError(f"Invalid or duplicate case in {split_name}")
            all_case_ids.add(case["id"])
            all_questions.add(normalized_question)
            expected = set(case["expected_relevant_passage_ids"])
            if not expected.issubset(passage_ids):
                raise ValueError(f"Case {case['id']} references a passage outside its split")
            if bool(expected) != bool(case["answer_present"]):
                raise ValueError(f"Case {case['id']} has inconsistent answerability labels")
            all_cases.append(case)
    if len(all_cases) < 100:
        raise ValueError("Retrieval evaluation requires at least 100 labeled cases")
    if not {"calibration", "validation", "holdout"}.issubset(dataset["splits"]):
        raise ValueError("Calibration, validation, and holdout splits are required")
    return True


def _embedding_key(text, task_type, configuration):
    return _canonical_hash({"text": text, "task_type": task_type, "configuration": configuration.as_dict()})


def _load_embedding_cache(path=CACHE_PATH):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("cache_version") != 1 or not isinstance(value.get("vectors"), dict):
            return {}
        dimensions = get_embedding_configuration().dimensions
        valid = {}
        for key, values in value["vectors"].items():
            try:
                vector = np.asarray(values, dtype=np.float64)
                norm = float(np.linalg.norm(vector))
            except (TypeError, ValueError):
                continue
            if (
                vector.ndim == 1 and vector.size == dimensions
                and np.isfinite(vector).all()
                and math.isfinite(norm) and math.isclose(norm, 1.0, rel_tol=1e-4, abs_tol=1e-4)
            ):
                valid[key] = vector.astype("float32").tolist()
        return valid
    except (OSError, ValueError, TypeError):
        return {}


def _save_embedding_cache(path, vectors):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps({"cache_version": 1, "vectors": vectors}, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def _cached_inputs(texts, task_type, cache, configuration):
    keys = [_embedding_key(text, task_type, configuration) for text in texts]
    missing = sorted({key for key in keys if key not in cache})
    return keys, missing


def estimate_usage(dataset, cache_path=CACHE_PATH):
    configuration = get_embedding_configuration()
    cache = _load_embedding_cache(cache_path)
    passages = [p["text"] for split in dataset["splits"].values() for p in split["passages"]]
    queries = [c["question"] for split in dataset["splits"].values() for c in split["cases"]]
    doc_keys, missing_docs = _cached_inputs(passages, configuration.document_task_type, cache, configuration)
    query_keys, missing_queries = _cached_inputs(queries, configuration.query_task_type, cache, configuration)
    # Count unique uncached inputs, since identical text/config/task can reuse one vector.
    requests = math.ceil(len(missing_docs) / MAX_BATCH_SIZE) + math.ceil(len(missing_queries) / MAX_BATCH_SIZE)
    max_attempts = requests * MAX_ATTEMPTS
    missing_doc_text = {key: text for text, key in zip(passages, doc_keys) if key in missing_docs}
    missing_query_text = {key: text for text, key in zip(queries, query_keys) if key in missing_queries}
    characters = sum(map(len, missing_doc_text.values())) + sum(map(len, missing_query_text.values()))
    return {
        "model": configuration.model,
        "dimensions": configuration.dimensions,
        "document_task_type": configuration.document_task_type,
        "query_task_type": configuration.query_task_type,
        "batch_size": MAX_BATCH_SIZE,
        "uncached_document_inputs": len(missing_docs),
        "uncached_query_inputs": len(missing_queries),
        "estimated_api_requests": requests,
        "bounded_maximum_request_attempts": max_attempts,
        "input_characters": characters,
        "estimated_input_tokens_chars_div_4": math.ceil(characters / 4),
        "estimated_paid_standard_usd_chars_div_4": round(math.ceil(characters / 4) * 0.15 / 1_000_000, 8),
        "generation_requests": 0,
        "cache_path": str(cache_path),
        "dataset_sha256": dataset["sha256"],
        "split_cases": {name: len(split["cases"]) for name, split in dataset["splits"].items()},
        "split_passages": {name: len(split["passages"]) for name, split in dataset["splits"].items()},
    }


class _RequestBudgetExceeded(EmbeddingProviderError):
    pass


class _BudgetedModels:
    def __init__(self, models, budget):
        self._models = models
        self._budget = budget

    def embed_content(self, **kwargs):
        if self._budget["calls"] >= self._budget["limit"]:
            raise _RequestBudgetExceeded("Bounded Gemini embedding request-attempt budget reached")
        self._budget["calls"] += 1
        return self._models.embed_content(**kwargs)


class _BudgetedClient:
    def __init__(self, client, budget):
        # Keep the SDK owner alive: its destructor closes the underlying HTTP client.
        self._client = client
        self.models = _BudgetedModels(client.models, budget)


def embed_with_cache(dataset, cache_path=CACHE_PATH, provider=embedding_provider):
    configuration = get_embedding_configuration()
    usage = estimate_usage(dataset, cache_path)
    cache = _load_embedding_cache(cache_path)
    budget = {"calls": 0, "limit": usage["bounded_maximum_request_attempts"]}
    original_client = provider.client
    if usage["estimated_api_requests"]:
        provider.client = _BudgetedClient(provider._get_client(), budget)
    try:
        vectors_by_key = {}
        for split in dataset["splits"].values():
            for passage in split["passages"]:
                key = _embedding_key(passage["text"], configuration.document_task_type, configuration)
                if key in cache:
                    vectors_by_key[key] = cache[key]
        passages = [p["text"] for split in dataset["splits"].values() for p in split["passages"]]
        doc_keys, missing_docs = _cached_inputs(passages, configuration.document_task_type, cache, configuration)
        missing_doc_text = {}
        for text, key in zip(passages, doc_keys):
            if key not in cache:
                missing_doc_text.setdefault(key, text)
        ordered_doc_keys = list(missing_doc_text)
        for offset in range(0, len(ordered_doc_keys), MAX_BATCH_SIZE):
            batch_keys = ordered_doc_keys[offset:offset + MAX_BATCH_SIZE]
            vectors = provider.embed_documents([missing_doc_text[key] for key in batch_keys])
            for key, vector in zip(batch_keys, vectors):
                cache[key] = vector.tolist()
                vectors_by_key[key] = cache[key]
            _save_embedding_cache(cache_path, cache)

        queries = [c["question"] for split in dataset["splits"].values() for c in split["cases"]]
        query_keys, missing_queries = _cached_inputs(queries, configuration.query_task_type, cache, configuration)
        missing_query_text = {}
        for text, key in zip(queries, query_keys):
            if key not in cache:
                missing_query_text.setdefault(key, text)
        ordered_query_keys = list(missing_query_text)
        for offset in range(0, len(ordered_query_keys), MAX_BATCH_SIZE):
            batch_keys = ordered_query_keys[offset:offset + MAX_BATCH_SIZE]
            vectors = provider.embed_queries([missing_query_text[key] for key in batch_keys])
            for key, vector in zip(batch_keys, vectors):
                cache[key] = vector.tolist()
            _save_embedding_cache(cache_path, cache)
        return cache, budget["calls"], usage
    except Exception as error:
        raise EvaluationEmbeddingError(usage, budget["calls"], type(error).__name__) from None
    finally:
        provider.client = original_client


def _rank_split(split, cache, configuration):
    passages = split["passages"]
    passage_vectors = np.asarray([
        cache[_embedding_key(passage["text"], configuration.document_task_type, configuration)]
        for passage in passages
    ], dtype=np.float64)
    ranked = {}
    for case in split["cases"]:
        query_vector = np.asarray(
            cache[_embedding_key(case["question"], configuration.query_task_type, configuration)],
            dtype=np.float64,
        )
        distances = np.linalg.norm(passage_vectors - query_vector, axis=1)
        order = np.argsort(distances, kind="stable")
        ranked[case["id"]] = [
            {"passage_id": passages[int(index)]["id"], "distance": float(distances[index])}
            for index in order[:5]
        ]
    return ranked


def _ratio(numerator, denominator):
    return float(numerator / denominator) if denominator else 0.0


def _ranking_metrics(cases, ranked):
    by_category = {}
    flattened = []
    for case in cases:
        expected = set(case["expected_relevant_passage_ids"])
        results = ranked[case["id"]]
        flattened.append((case, expected, results))
        by_category.setdefault(case["category"], []).append((case, expected, results))

    def summarize(rows):
        output = {}
        for k in TOP_K_VALUES:
            recalls, precisions, reciprocal_ranks, ndcgs = [], [], [], []
            for case, expected, results in rows:
                top = results[:k]
                hits = [item["passage_id"] in expected for item in top]
                if expected:
                    recalls.append(_ratio(sum(hits), len(expected)))
                precisions.append(_ratio(sum(hits), k))
                ranks = [index + 1 for index, hit in enumerate(hits) if hit]
                reciprocal_ranks.append(1 / ranks[0] if ranks else 0.0)
                dcg = sum((1 / math.log2(index + 2)) for index, hit in enumerate(hits) if hit)
                ideal_hits = min(len(expected), k)
                idcg = sum(1 / math.log2(index + 2) for index in range(ideal_hits))
                ndcgs.append(_ratio(dcg, idcg))
            output[str(k)] = {
                "recall": _ratio(sum(recalls), len(recalls)),
                "precision": _ratio(sum(precisions), len(precisions)),
                "mrr": _ratio(sum(reciprocal_ranks), len(reciprocal_ranks)),
                "ndcg": _ratio(sum(ndcgs), len(ndcgs)),
                "answerable_cases": len(recalls),
                "total_cases": len(rows),
            }
        return output

    return {
        "overall": summarize(flattened),
        "by_category": {category: summarize(rows) for category, rows in sorted(by_category.items())},
    }


def _threshold_metrics(cases, ranked, threshold):
    labels, predictions = [], []
    no_answer = []
    coverage = []
    for case in cases:
        results = ranked[case["id"]]
        expected = set(case["expected_relevant_passage_ids"])
        selected = []
        for item in results:
            label = item["passage_id"] in expected
            predicted = item["distance"] <= threshold
            labels.append(label)
            predictions.append(predicted)
            if predicted:
                selected.append(item)
        coverage.append(bool(selected))
        if not case["answer_present"]:
            no_answer.append(not selected)
    tp = sum(y and p for y, p in zip(labels, predictions))
    fp = sum((not y) and p for y, p in zip(labels, predictions))
    fn = sum(y and (not p) for y, p in zip(labels, predictions))
    tn = sum((not y) and (not p) for y, p in zip(labels, predictions))
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    return {
        "threshold": float(threshold),
        "comparison": "distance <= threshold",
        "true_positive": tp, "false_positive": fp,
        "false_negative": fn, "true_negative": tn,
        "precision": precision, "recall": recall,
        "false_positive_rate": _ratio(fp, fp + tn),
        "false_negative_rate": _ratio(fn, fn + tp),
        "coverage": _ratio(sum(coverage), len(coverage)),
        "no_answer_rejection_rate": _ratio(sum(no_answer), len(no_answer)),
        "no_answer_cases": len(no_answer),
    }


def _calibrate(cases, ranked):
    distances = sorted({item["distance"] for case in cases for item in ranked[case["id"]]})
    candidates = [math.nextafter(distances[0], -math.inf), *distances]
    eligible = []
    for threshold in candidates:
        metrics = _threshold_metrics(cases, ranked, threshold)
        if metrics["false_positive_rate"] <= FALSE_POSITIVE_RATE_CEILING:
            eligible.append(metrics)
    if not eligible:
        return None, None
    selected = max(eligible, key=lambda item: (item["recall"], item["precision"], -item["threshold"]))
    if selected["true_positive"] == 0:
        return None, {"reason": "No threshold within the approved false-positive ceiling retrieves any relevant passage", **selected}
    return selected["threshold"], selected


def _distance_distributions(cases, ranked):
    positives, negatives = [], []
    for case in cases:
        expected = set(case["expected_relevant_passage_ids"])
        for item in ranked[case["id"]]:
            (positives if item["passage_id"] in expected else negatives).append(item["distance"])
    def stats(values):
        if not values:
            return {"count": 0}
        data = np.asarray(values)
        return {
            "count": int(data.size), "min": float(data.min()), "p25": float(np.quantile(data, .25)),
            "median": float(np.median(data)), "p75": float(np.quantile(data, .75)),
            "max": float(data.max()), "mean": float(data.mean()),
        }
    return {"relevant_top5": stats(positives), "irrelevant_top5": stats(negatives)}


def evaluate(dataset=None, cache_path=CACHE_PATH, execute=False, write_calibration=False):
    dataset = dataset or load_dataset()
    usage = estimate_usage(dataset, cache_path)
    if not execute:
        return {"mode": "dry_run", "usage": usage}
    cache, actual_calls, usage = embed_with_cache(dataset, cache_path)
    configuration = get_embedding_configuration()
    ranked = {
        name: _rank_split(split, cache, configuration)
        for name, split in dataset["splits"].items()
    }
    calibration_cases = dataset["splits"]["calibration"]["cases"]
    threshold, calibration_metrics = _calibrate(calibration_cases, ranked["calibration"])
    result = {
        "evaluation_version": "gemini-retrieval-eval-v1",
        "dataset_version": dataset["version"],
        "dataset_sha256": dataset["sha256"],
        "configuration": configuration.as_dict(),
        "chunking": chunker.get_chunking_configuration(),
        "distance_convention": "ordinary Euclidean L2 distance returned by pgvector <->; not squared L2",
        "retrieval_top_k": 5,
        "ranking_k_values": list(TOP_K_VALUES),
        "threshold_policy": {
            "selection": "maximize calibration recall subject to chunk-level false-positive rate <= 0.05; then precision; then smaller threshold",
            "comparison": "distance <= threshold",
            "false_positive_rate_ceiling": FALSE_POSITIVE_RATE_CEILING,
        },
        "usage": {**usage, "actual_api_request_attempts": actual_calls},
        "distance_distributions": {
            name: _distance_distributions(split["cases"], ranked[name])
            for name, split in dataset["splits"].items()
        },
        "ranking_metrics": {
            name: _ranking_metrics(split["cases"], ranked[name])
            for name, split in dataset["splits"].items()
        },
        "calibration_metrics": calibration_metrics,
        "validation_threshold_metrics": _threshold_metrics(
            dataset["splits"]["validation"]["cases"], ranked["validation"], threshold
        ) if threshold is not None else None,
        "holdout_threshold_metrics": _threshold_metrics(
            dataset["splits"]["holdout"]["cases"], ranked["holdout"], threshold
        ) if threshold is not None else None,
        "calibration_status": "calibrated" if threshold is not None else "inconclusive",
        "threshold": threshold,
        "calibrated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    if threshold is not None and write_calibration:
        if CALIBRATION_PATH.exists():
            raise FileExistsError(f"Refusing to overwrite existing Gemini calibration: {CALIBRATION_PATH}")
        artifact = {
            "calibration_status": "calibrated",
            **configuration.as_dict(),
            "embedding_provider": configuration.provider,
            "embedding_model": configuration.model,
            "dimensions": configuration.dimensions,
            "metric": configuration.distance_metric,
            "distance_convention": "euclidean_l2_unsquared",
            "normalization": configuration.normalization,
            "chunking": chunker.get_chunking_configuration(),
            "retrieval_top_k": 5,
            "dataset_version": dataset["version"],
            "dataset_sha256": dataset["sha256"],
            "calibrated_at_utc": result["calibrated_at_utc"],
            "max_distance": threshold,
            "threshold_comparison": "<=",
            "threshold_policy": result["threshold_policy"],
            "calibration_metrics": calibration_metrics,
            "validation_metrics": result["validation_threshold_metrics"],
            "holdout_metrics": result["holdout_threshold_metrics"],
            "ranking_metrics": result["ranking_metrics"],
            "distance_distributions": result["distance_distributions"],
        }
        # Stage the complete artifact beside its destination, then atomically
        # publish without replacing an artifact created by another process.
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=CALIBRATION_PATH.parent,
                prefix=CALIBRATION_PATH.name + ".", suffix=".tmp", delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(json.dumps(artifact, indent=2) + "\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.link(temporary_path, CALIBRATION_PATH)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        result["calibration_artifact"] = str(CALIBRATION_PATH.relative_to(BACKEND_DIR))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calibrate Gemini retrieval; dry-run makes no API calls.")
    parser.add_argument("--execute", action="store_true", help="Generate only missing Gemini embeddings and evaluate")
    parser.add_argument("--write-calibration", action="store_true", help="Write a new Gemini artifact; never overwrites an existing one")
    args = parser.parse_args()
    if args.write_calibration and not args.execute:
        parser.error("--write-calibration requires --execute")
    try:
        output = evaluate(execute=args.execute, write_calibration=args.write_calibration)
    except EvaluationEmbeddingError as error:
        output = {
            "evaluation_status": "embedding_failed",
            "dataset_version": load_dataset()["version"],
            "usage": {**error.usage, "actual_api_request_attempts": error.request_attempts},
            "failure_type": error.cause_type,
            "threshold": None,
            "calibration_artifact_written": False,
        }
        report_dir = BACKEND_DIR / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"gemini_retrieval_evaluation_failed_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
        if report_path.exists():
            raise FileExistsError(f"Refusing to overwrite evaluation report: {report_path}")
        output["report_path"] = str(report_path.relative_to(BACKEND_DIR))
        report_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(output, indent=2))
        raise SystemExit(2)
    if args.execute:
        report_dir = BACKEND_DIR / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"gemini_retrieval_evaluation_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
        if report_path.exists():
            raise FileExistsError(f"Refusing to overwrite evaluation report: {report_path}")
        output["report_path"] = str(report_path.relative_to(BACKEND_DIR))
        report_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
