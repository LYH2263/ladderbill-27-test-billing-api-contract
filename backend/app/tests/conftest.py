"""Shared fixtures for the billing API contract tests.

The app is exercised in-process through FastAPI's TestClient: no browser,
no frontend build, no live server. A throwaway DATA_DIR is set before any
app module is imported (conftest is imported before test modules), so the
seeded SQLite database is created fresh for the run and real data is never
touched.
"""

import os
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="ladderbill-contract-")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    # Entering the context runs startup handlers, which seed the database.
    with TestClient(app) as c:
        yield c
