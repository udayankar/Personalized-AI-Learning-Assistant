"""Opt-in real PostgreSQL + pgvector retrieval integration test.

Set PGVECTOR_TEST_DATABASE_URL to a migrated PostgreSQL database. All test rows
run in an outer transaction and are rolled back; Gemini is mocked.
"""
import os
import unittest
import uuid
from unittest.mock import patch

from pgvector.psycopg import register_vector
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from App.models import Document, DocumentChunk, User
from Rag import vector_store


@unittest.skipUnless(os.getenv("PGVECTOR_TEST_DATABASE_URL"), "requires PGVECTOR_TEST_DATABASE_URL")
class NeonPgvectorRetrievalTests(unittest.TestCase):
    def test_real_l2_search_filters_user_and_ready_status(self):
        engine = create_engine(os.environ["PGVECTOR_TEST_DATABASE_URL"], pool_pre_ping=True)
        event.listen(engine, "connect", lambda connection, _record: register_vector(connection))
        connection = engine.connect()
        transaction = connection.begin()
        session = Session(bind=connection, expire_on_commit=False)

        class ReuseSession:
            def __enter__(self):
                return session
            def __exit__(self, *_args):
                return False

        def same_transaction_session():
            return ReuseSession()

        first_id = 1_800_000_000 + uuid.uuid4().int % 100_000_000
        second_id = first_id + 1
        suffix = uuid.uuid4().hex
        try:
            installed = session.scalar(text(
                "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"
            ))
            self.assertTrue(installed, "pgvector extension must be enabled by Alembic")
            session.add_all([
                User(ID=first_id, Name="Integration A", Email=f"a-{suffix}@test.invalid", Password="x"),
                User(ID=second_id, Name="Integration B", Email=f"b-{suffix}@test.invalid", Password="x"),
            ])
            session.flush()
            ready = Document(user_id=first_id, filename="ready.pdf", storage_filename=f"a-{suffix}",
                             file_size_bytes=1, page_count=1, sha256="a" * 64, status="READY")
            processing = Document(user_id=first_id, filename="processing.pdf", storage_filename=f"p-{suffix}",
                                  file_size_bytes=1, page_count=1, sha256="b" * 64, status="PROCESSING")
            private = Document(user_id=second_id, filename="private.pdf", storage_filename=f"b-{suffix}",
                               file_size_bytes=1, page_count=1, sha256="c" * 64, status="READY")
            session.add_all([ready, processing, private])
            session.flush()
            near = [1.0] + [0.0] * 767
            far = [0.0, 1.0] + [0.0] * 766
            for owner, doc, position, text_value, vector in [
                (first_id, ready, 0, "owner ready", near),
                (first_id, ready, 1, "second owner passage", far),
                (first_id, processing, 0, "must be hidden", near),
                (second_id, private, 0, "must not leak", near),
            ]:
                session.add(DocumentChunk(
                    user_id=owner, document_id=doc.id, chunk_index=position, text=text_value,
                    page_number=1, embedding=vector, embedding_provider="gemini",
                    embedding_model="gemini-embedding-001", embedding_dimensions=768,
                    embedding_task_type="RETRIEVAL_DOCUMENT",
                ))
            session.flush()
            with patch.object(vector_store, "SessionLocal", same_transaction_session), \
                 patch.object(vector_store, "Get_calibrated_relevance_threshold", return_value=2.0):
                result = vector_store.Retrieve(
                    "sample query", type("FakeEmbedder", (), {"embed_query": lambda self, _query: near})(),
                    first_id, k=5,
                )
            self.assertEqual([chunk.text for chunk in result.chunks], ["owner ready", "second owner passage"])
            self.assertEqual([chunk.distance for chunk in result.chunks], [0.0, 2**0.5])
        finally:
            session.close()
            transaction.rollback()
            connection.close()
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
