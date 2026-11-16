import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


class DocumentMigrationTests(unittest.TestCase):
    def test_document_catalog_migration_upgrades_and_downgrades_on_isolated_database(self):
        backend_dir = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "migration-test.sqlite"
            database_url = f"sqlite:///{database_path.as_posix()}"
            config = Config(str(backend_dir / "alembic.ini"))
            with patch.dict(os.environ, {"DATABASE_URL": database_url}):
                command.upgrade(config, "c2b9d8417e6a")
                engine = create_engine(database_url)
                try:
                    with engine.begin() as connection:
                        connection.execute(text(
                            'INSERT INTO users ("Name", "Email", "Password", "Created_at") '
                            'VALUES (:name, :email, :password, :created_at)'
                        ), {
                            "name": "Legacy", "email": "legacy@example.test",
                            "password": "hashed", "created_at": "2026-11-16 00:00:00+00:00",
                        })
                        user_id = connection.scalar(text(
                            'SELECT "ID" FROM users WHERE "Email" = :email'
                        ), {"email": "legacy@example.test"})
                        connection.execute(text(
                            "INSERT INTO answer_cache "
                            "(user_id, normalized_query_hash, answer, answer_mode, reliability, "
                            "conflict_status, claims, sources, context_fingerprint, pipeline_version, "
                            "gemini_calls, created_at, expires_at) "
                            "VALUES (:user_id, :query_hash, :answer, 'GENERAL_KNOWLEDGE', 'MODERATE', "
                            "'NONE', '[]', '[]', :context, :pipeline, 1, :created_at, :expires_at)"
                        ), {
                            "user_id": user_id,
                            "query_hash": "q" * 64,
                            "answer": "A legacy general answer",
                            "context": "c" * 64,
                            "pipeline": "old-pipeline",
                            "created_at": "2026-11-16 00:00:00+00:00",
                            "expires_at": "2026-11-17 00:00:00+00:00",
                        })
                finally:
                    engine.dispose()

                command.upgrade(config, "head")
                engine = create_engine(database_url)
                try:
                    inspector = inspect(engine)
                    self.assertIn("documents", inspector.get_table_names())
                    checks = {item["name"]: item["sqltext"] for item in inspector.get_check_constraints("answer_cache")}
                    self.assertIn("INSUFFICIENT_CONFIDENCE", checks["ck_answer_cache_answer_mode"])
                    self.assertNotIn("GENERAL_KNOWLEDGE", checks["ck_answer_cache_answer_mode"])
                    with engine.connect() as connection:
                        self.assertEqual(connection.execute(
                            text("SELECT COUNT(*) FROM answer_cache")
                        ).scalar_one(), 0)
                    columns = {item["name"]: item for item in inspector.get_columns("documents")}
                    self.assertEqual(
                        set(columns),
                        {
                            "id", "user_id", "filename", "storage_filename",
                            "file_size_bytes", "page_count", "sha256", "status",
                            "uploaded_at", "updated_at",
                        },
                    )
                    self.assertTrue(columns["page_count"]["nullable"])
                    self.assertEqual(
                        {tuple(item["column_names"]) for item in inspector.get_unique_constraints("documents")},
                        {("user_id", "storage_filename")},
                    )
                    foreign_keys = inspector.get_foreign_keys("documents")
                    self.assertEqual(len(foreign_keys), 1)
                    self.assertEqual(foreign_keys[0]["constrained_columns"], ["user_id"])
                    self.assertEqual(foreign_keys[0]["referred_table"], "users")
                    self.assertEqual(foreign_keys[0]["referred_columns"], ["ID"])
                    self.assertEqual(foreign_keys[0]["options"].get("ondelete"), "CASCADE")
                finally:
                    engine.dispose()

                command.downgrade(config, "c2b9d8417e6a")
                engine = create_engine(database_url)
                try:
                    self.assertNotIn("documents", inspect(engine).get_table_names())
                    self.assertIn("answer_cache", inspect(engine).get_table_names())
                finally:
                    engine.dispose()


if __name__ == "__main__":
    unittest.main()
