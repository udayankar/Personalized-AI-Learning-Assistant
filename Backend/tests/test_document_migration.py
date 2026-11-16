import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


class DocumentMigrationTests(unittest.TestCase):
    def test_document_catalog_migration_upgrades_and_downgrades_on_isolated_database(self):
        backend_dir = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "migration-test.sqlite"
            database_url = f"sqlite:///{database_path.as_posix()}"
            config = Config(str(backend_dir / "alembic.ini"))
            with patch.dict(os.environ, {"DATABASE_URL": database_url}):
                command.upgrade(config, "head")
                engine = create_engine(database_url)
                try:
                    inspector = inspect(engine)
                    self.assertIn("documents", inspector.get_table_names())
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
