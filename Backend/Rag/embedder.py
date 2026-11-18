import logging
import math
import os
from dataclasses import dataclass
import numpy as np
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)
DEFAULT_PROVIDER = "gemini"
DEFAULT_MODEL = "gemini-embedding-001"
DEFAULT_DIMENSIONS = 768
DOCUMENT_TASK = "RETRIEVAL_DOCUMENT"
QUERY_TASK = "RETRIEVAL_QUERY"
DISTANCE_METRIC = "l2"
NORMALIZATION = "l2_unit"
MAX_BATCH_SIZE = 100
MAX_ATTEMPTS = 1
REQUEST_TIMEOUT_MS = 900_000

@dataclass(frozen=True)
class EmbeddingConfiguration:
    provider: str
    model: str
    dimensions: int
    document_task_type: str
    query_task_type: str
    normalization: str
    distance_metric: str
    batch_size: int

    def as_dict(self):
        return {
            "provider": self.provider, "model": self.model,
            "dimensions": self.dimensions,
            "document_task_type": self.document_task_type,
            "query_task_type": self.query_task_type,
            "normalization": self.normalization,
            "distance_metric": self.distance_metric,
            "batch_size": self.batch_size,
        }


def get_embedding_configuration() -> EmbeddingConfiguration:
    provider = os.getenv("EMBEDDING_PROVIDER", DEFAULT_PROVIDER).strip().lower()
    model = os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL).strip()
    raw_dimensions = os.getenv("EMBEDDING_DIMENSIONS", str(DEFAULT_DIMENSIONS))
    try:
        dimensions = int(raw_dimensions)
    except (TypeError, ValueError) as error:
        raise ValueError("EMBEDDING_DIMENSIONS must be an integer") from error
    if provider != "gemini":
        raise ValueError("EMBEDDING_PROVIDER currently supports only 'gemini'")
    if model != DEFAULT_MODEL:
        raise ValueError("EMBEDDING_MODEL must be gemini-embedding-001")
    if dimensions != DEFAULT_DIMENSIONS:
        raise ValueError("EMBEDDING_DIMENSIONS must be 768 for pgvector")
    return EmbeddingConfiguration(
        provider, model, dimensions, DOCUMENT_TASK, QUERY_TASK, NORMALIZATION,
        DISTANCE_METRIC, MAX_BATCH_SIZE,
    )


class EmbeddingProviderError(RuntimeError):
    """A Gemini embedding request failed or returned an unusable response."""


class GeminiEmbedder:
    def __init__(self, client=None, configuration=None):
        self.configuration = configuration or get_embedding_configuration()
        self.client = client

    def embed_documents(self, texts):
        return self._embed_many(texts, DOCUMENT_TASK)

    def embed_queries(self, texts):
        """Embed multiple queries in retrieval-query batches for offline evaluation."""
        return self._embed_many(texts, QUERY_TASK)

    def embed_query(self, text):
        vectors = self._embed_many([text], QUERY_TASK)
        return vectors[0]

    def _embed_many(self, texts, task_type):
        if not isinstance(texts, (list, tuple)) or any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("Embedding inputs must be non-empty strings")
        output = []
        for offset in range(0, len(texts), self.configuration.batch_size):
            batch = texts[offset:offset + self.configuration.batch_size]
            response = self._request(batch, task_type)
            embeddings = getattr(response, "embeddings", None)
            if not isinstance(embeddings, (list, tuple)) or len(embeddings) != len(batch):
                raise EmbeddingProviderError("Gemini returned an invalid number of embeddings")
            for item in embeddings:
                values = getattr(item, "values", None)
                try:
                    vector = np.asarray(values, dtype=np.float64)
                except (TypeError, ValueError) as error:
                    raise EmbeddingProviderError("Gemini returned an invalid embedding vector") from error
                if vector.ndim != 1 or vector.size != self.configuration.dimensions:
                    raise EmbeddingProviderError("Gemini returned an embedding with an unexpected dimension")
                if not np.isfinite(vector).all():
                    raise EmbeddingProviderError("Gemini returned NaN or infinite embedding values")
                norm = float(np.linalg.norm(vector))
                if not math.isfinite(norm) or norm <= 0:
                    raise EmbeddingProviderError("Gemini returned a zero or invalid embedding vector")
                output.append((vector / norm).astype("float32"))
        return np.asarray(output, dtype="float32")

    def _request(self, batch, task_type):
        try:
            return self._get_client().models.embed_content(
                model=self.configuration.model,
                contents=list(batch),
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=self.configuration.dimensions,
                ),
            )
        except EmbeddingProviderError:
            raise
        except Exception as error:
            status = getattr(error, "code", None) or getattr(error, "status_code", None)
            logger.error(
                "gemini_embedding_failed model=%s task_type=%s http_status=%s error_type=%s",
                self.configuration.model, task_type, status, type(error).__name__,
            )
            raise EmbeddingProviderError("Gemini embedding request failed") from error

    def _get_client(self):
        if self.client is None:
            api_key = os.getenv("LLM_API_KEY", "").strip()
            if not api_key:
                raise EmbeddingProviderError("LLM_API_KEY is required for Gemini embeddings")
            self.client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    timeout=REQUEST_TIMEOUT_MS,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
        return self.client

embedding_provider = GeminiEmbedder()

def Create_embeddings(chunks):
    return embedding_provider.embed_documents([chunk["text"] for chunk in chunks])
