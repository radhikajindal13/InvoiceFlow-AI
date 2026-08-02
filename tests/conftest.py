import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("MISTRAL_API_KEY", "test-key-not-used")


@pytest.fixture()
def temp_db(monkeypatch):
    """Point database.db at a throwaway sqlite file for this test only,
    then run the real schema DDL against it."""
    tmp_dir = tempfile.mkdtemp()
    db_path = Path(tmp_dir) / "test.db"

    import database.db as db_module
    monkeypatch.setattr(db_module, "DB_PATH", db_path)

    import database.schema as schema_module
    schema_module.initialize_database()

    yield db_path
