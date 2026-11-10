import pytest

from fiberlab.backend.seed import create_database


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Every test gets its own fresh synthetic database."""
    db = create_database(tmp_path / "fiberlab.db")
    monkeypatch.setenv("FIBERLAB_DB", str(db))
    monkeypatch.setenv("FIBERLAB_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")  # tests never send traces or use your quota
    return db
