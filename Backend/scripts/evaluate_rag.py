import argparse
import json
import sys
from pathlib import Path
import faiss
import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from Rag.embedder import model
from Rag.relevance import Calibrate_distance_threshold, Score_binary_labels


DATASET_PATH = BACKEND_DIR / "tests" / "fixtures" / "rag_evaluation.json"
CALIBRATION_PATH = BACKEND_DIR / "Rag" / "retrieval_calibration.json"


def _metrics_for_cases(cases, retrieved_by_case, threshold):
    labels = []
    predictions = []
    case_labels = []
    case_predictions = []
    relevant_recall = []
    complete_support = []
    for case in cases:
        retrieved = retrieved_by_case[case["id"]]
        supporting_ids = set(case["expected_supporting_passage_ids"])
        labels.extend(item["passage_id"] in supporting_ids for item in retrieved)
        predictions.extend(item["distance"] <= threshold for item in retrieved)
        case_labels.append(bool(case["evidence_sufficient"]))
        case_predictions.append(any(item["distance"] <= threshold for item in retrieved))
        if supporting_ids:
            found = {item["passage_id"] for item in retrieved}
            relevant_recall.append(len(found & supporting_ids) / len(supporting_ids))
            complete_support.append(float(supporting_ids.issubset(found)))
    return {
        "retrieved_chunk_relevance": Score_binary_labels(labels, predictions),
        "evidence_sufficiency": Score_binary_labels(case_labels, case_predictions),
        "support_passage_recall_at_5": sum(relevant_recall) / len(relevant_recall) if relevant_recall else 0.0,
        "complete_support_at_5": sum(complete_support) / len(complete_support) if complete_support else 0.0,
    }


def evaluate(write_calibration=False):
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    passages = []
    for document in dataset["documents"]:
        for page in document["pages"]:
            for passage in page["passages"]:
                passages.append({
                    "passage_id": passage["id"],
                    "document_id": document["id"],
                    "source": document["source"],
                    "page": page["page"],
                    "text": passage["text"],
                })

    embeddings = np.asarray(
        model.encode([passage["text"] for passage in passages], show_progress_bar=False),
        dtype="float32",
    )
    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings)

    retrieved_by_case = {}
    for case in dataset["cases"]:
        results = []
        if not case.get("knowledge_base_empty", False):
            query_embedding = np.asarray(
                model.encode(case["question"], show_progress_bar=False), dtype="float32"
            ).reshape(1, -1)
            distances, indices = index.search(query_embedding, min(dataset["top_k"], index.ntotal))
            for distance, passage_index in zip(distances[0], indices[0]):
                if passage_index < 0 or passage_index >= len(passages):
                    continue
                results.append({
                    "passage_id": passages[passage_index]["passage_id"],
                    "distance": float(distance),
                })
        retrieved_by_case[case["id"]] = results

    calibration_cases = [case for case in dataset["cases"] if case["split"] == "calibration"]
    validation_cases = [case for case in dataset["cases"] if case["split"] == "validation"]
    calibration_samples = []
    for case in calibration_cases:
        supporting_ids = set(case["expected_supporting_passage_ids"])
        calibration_samples.extend(
            (item["distance"], item["passage_id"] in supporting_ids)
            for item in retrieved_by_case[case["id"]]
        )
    threshold, calibration_fit = Calibrate_distance_threshold(calibration_samples)
    output = {
        "dataset_cases": len(dataset["cases"]),
        "calibration_cases": len(calibration_cases),
        "validation_cases": len(validation_cases),
        "embedding_model": dataset["embedding_model"],
        "metric": dataset["metric"],
        "top_k": dataset["top_k"],
        "max_squared_l2_distance": threshold,
        "calibration_fit": calibration_fit,
        "validation": _metrics_for_cases(validation_cases, retrieved_by_case, threshold),
    }

    if write_calibration:
        CALIBRATION_PATH.write_text(
            json.dumps(output, indent=2) + "\n", encoding="utf-8"
        )
        output["calibration_file_written"] = str(CALIBRATION_PATH.relative_to(BACKEND_DIR))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate and calibrate the current RAG retriever.")
    parser.add_argument(
        "--write-calibration",
        action="store_true",
        help="Persist the calibration artifact consumed by runtime retrieval.",
    )
    args = parser.parse_args()
    print(json.dumps(evaluate(write_calibration=args.write_calibration), indent=2))
