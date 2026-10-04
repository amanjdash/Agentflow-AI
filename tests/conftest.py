"""Pytest fixtures for AgentFlow test suite."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Generator
import pytest
from fastapi.testclient import TestClient

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.seed import seed_database
from app.main import app


@pytest.fixture(scope="session")
def test_db() -> Generator[Path, None, None]:
    """Creates a temporary seeded database for the duration of the test session."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_path = Path(tf.name)

    seed_database(temp_path)
    os.environ["DATABASE_PATH"] = str(temp_path)

    yield temp_path

    # Teardown
    if temp_path.exists():
        try:
            temp_path.unlink()
        except Exception:
            pass


@pytest.fixture
def client(test_db: Path) -> Generator[TestClient, None, None]:
    """FastAPI TestClient fixture configured with the test database."""
    with TestClient(app) as test_client:
        yield test_client
