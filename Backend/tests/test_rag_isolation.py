import math
import unittest
from unittest.mock import Mock
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from App.base import Base
from App.models import Document, DocumentChunk, User
from Rag import vector_store
from Rag.chunker import Chunk_Txt


class PgvectorChunkIsolationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        @event.listens_for(self.engine, "connect")
        def _foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.session_patch = patch.object(vector_store, "SessionLocal", self.Session)
        self.session_patch.start()
        self.addCleanup(self.session_patch.stop)
        self.addCleanup(self.engine.dispose)
        self.config = type("Config", (), {
            "provider": "gemini", "model": "gemini-embedding-001", "dimensions": 768,
            "document_task_type": "RETRIEVAL_DOCUMENT", "query_task_type": "RETRIEVAL_QUERY",
            "normalization": "l2_unit", "distance_metric": "l2", "batch_size": 100,
            "as_dict": lambda self: {"provider": self.provider, "model": self.model,
                                     "dimensions": self.dimensions, "document_task_type": self.document_task_type},
        })()
        self.config_patch = patch.object(vector_store, "get_embedding_configuration", return_value=self.config)
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.threshold_patch = patch.object(vector_store, "Get_calibrated_relevance_threshold", return_value=0.5)
        self.threshold_patch.start()
        self.addCleanup(self.threshold_patch.stop)
        with self.Session() as session:
            session.add_all([
                User(ID=101, Name="A", Email="a@example.test", Password="hash"),
                User(ID=202, Name="B", Email="b@example.test", Password="hash"),
            ])
            session.commit()

    @staticmethod
    def _unit_vector(index=0):
        value = [0.0] * 768
        value[index] = 1.0
        return value

    def _document(self, session, user_id, name, status="READY"):
        document = Document(user_id=user_id, filename=name, storage_filename=f"{user_id}-{name}",
                            file_size_bytes=10, page_count=1, sha256="a" * 64, status=status)
        session.add(document)
        session.flush()
        return document

    def _chunk(self, session, user_id, document, text, index=0, vector=None):
        row = DocumentChunk(
            user_id=user_id, document_id=document.id, chunk_index=index, text=text,
            page_number=1, embedding=vector or self._unit_vector(),
            embedding_provider="gemini", embedding_model="gemini-embedding-001",
            embedding_dimensions=768, embedding_task_type="RETRIEVAL_DOCUMENT",
        )
        session.add(row)
        return row

    def test_embedding_validation_rejects_wrong_dimensions_nan_and_non_unit_vectors(self):
        with self.assertRaises(ValueError):
            vector_store.validate_chunk_embedding([1.0, 0.0])
        with self.assertRaises(ValueError):
            vector_store.validate_chunk_embedding([float("nan")] + [0.0] * 767)
        with self.assertRaises(ValueError):
            vector_store.validate_chunk_embedding([2.0] + [0.0] * 767)
        self.assertTrue(math.isclose(sum(x*x for x in vector_store.validate_chunk_embedding(self._unit_vector())), 1.0))

    def test_chunk_insert_uses_document_task_type_and_unique_positions(self):
        document_chunks = [{"text": "first", "page": 2}, {"text": "second", "page": 2}]
        vectors = [self._unit_vector(), self._unit_vector(1)]
        with self.Session() as session:
            document = self._document(session, 101, "notes.pdf", "PROCESSING")
            vector_store.Insert_document_chunks(session, document, document_chunks, vectors)
            document.status = "READY"
            session.commit()
            rows = session.query(DocumentChunk).filter_by(document_id=document.id).order_by(DocumentChunk.chunk_index).all()
            self.assertEqual([row.chunk_index for row in rows], [0, 1])
            self.assertEqual([row.embedding_task_type for row in rows], ["RETRIEVAL_DOCUMENT"] * 2)
            self.assertEqual([row.embedding_dimensions for row in rows], [768, 768])
            self.assertEqual([row.page_number for row in rows], [2, 2])

    def test_chunk_insertion_rejects_mismatched_vector_count(self):
        with self.Session() as session:
            document = self._document(session, 101, "notes.pdf", "PROCESSING")
            with self.assertRaises(ValueError):
                vector_store.Insert_document_chunks(session, document, [{"text": "one"}], [])

    def test_cache_provenance_loader_is_scoped_to_owner_and_ready_documents(self):
        with self.Session() as session:
            ready = self._document(session, 101, "ready.pdf")
            processing = self._document(session, 101, "processing.pdf", "PROCESSING")
            other = self._document(session, 202, "private.pdf")
            self._chunk(session, 101, ready, "owner text")
            self._chunk(session, 101, processing, "not ready")
            self._chunk(session, 202, other, "private text")
            session.commit()
        chunks = vector_store.Load_ready_chunk_metadata(101)
        self.assertEqual([chunk["text"] for chunk in chunks], ["owner text"])
        self.assertEqual(chunks[0]["user_id"], 101)

    def test_composite_foreign_key_prevents_chunk_tenant_mismatch(self):
        with self.Session() as session:
            document = self._document(session, 101, "owner.pdf")
            session.commit()
            session.add(DocumentChunk(
                user_id=202, document_id=document.id, chunk_index=0, text="forged",
                embedding=self._unit_vector(), embedding_provider="gemini",
                embedding_model="gemini-embedding-001", embedding_dimensions=768,
                embedding_task_type="RETRIEVAL_DOCUMENT",
            ))
            with self.assertRaises(Exception):
                session.commit()

    def test_duplicate_chunk_position_is_rejected(self):
        with self.Session() as session:
            document = self._document(session, 101, "notes.pdf")
            self._chunk(session, 101, document, "one")
            self._chunk(session, 101, document, "duplicate")
            with self.assertRaises(Exception):
                session.commit()

    def test_empty_ready_collection_does_not_call_embedding_provider(self):
        embedder = Mock()
        result = vector_store.Retrieve("query", embedder, 101)
        self.assertEqual(result.chunks, ())
        embedder.embed_query.assert_not_called()

    def test_mismatched_stored_embedding_is_rejected_before_provider_call(self):
        with self.Session() as session:
            document = self._document(session, 101, "old-space.pdf")
            row = self._chunk(session, 101, document, "old vector")
            row.embedding_provider = "minilm"
            session.commit()
        embedder = Mock()
        with self.assertRaises(vector_store.IncompatibleVectorStoreError):
            vector_store.Retrieve("query", embedder, 101)
        embedder.embed_query.assert_not_called()

    def test_document_delete_cascades_chunks(self):
        with self.Session() as session:
            document = self._document(session, 101, "notes.pdf")
            self._chunk(session, 101, document, "chunk")
            session.commit()
            document_id = document.id
            session.delete(document)
            session.commit()
            self.assertEqual(session.query(DocumentChunk).filter_by(document_id=document_id).count(), 0)

    def test_retrieval_result_keeps_provenance_and_applies_l2_threshold(self):
        result = vector_store.Make_retrieval_result("query", 101, [{
            "source": "notes.pdf", "document_id": "doc", "page": 4,
            "text": "passage", "user_id": 101, "distance": 0.2,
        }], 0.5)
        self.assertTrue(result.evidence_sufficient)
        self.assertEqual(result.sources, [{"source": "notes.pdf", "page": 4, "text": "passage"}])
        with self.assertRaises(ValueError):
            vector_store.Make_retrieval_result("query", 101, [{
                "source": "private.pdf", "text": "private", "user_id": 202, "distance": 0.1,
            }], 0.5)

    def test_local_chunker_keeps_page_provenance_and_configured_character_limit(self):
        text = "word " * 500
        chunks = Chunk_Txt([{"page": 3, "text": text}])
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk["text"]) <= 1000 for chunk in chunks))
        self.assertTrue(all(chunk["page"] == 3 for chunk in chunks))
        self.assertGreater(len(set(chunks[0]["text"].split()) & set(chunks[1]["text"].split())), 0)


if __name__ == "__main__":
    unittest.main()
