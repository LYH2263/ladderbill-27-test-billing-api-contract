import os
import sys
from pathlib import Path

import pytest

# Make the backend root (the directory containing the ``app`` package)
# importable no matter where pytest is invoked from.
BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Point the app at an isolated SQLite data dir BEFORE any ``app.*`` import:
# app.config / app.db read DATA_DIR at import time. This keeps contract tests
# off any real database and makes them self-contained in CI.
_TEST_DATA_DIR = BACKEND_ROOT / ".pytest-data"
os.environ["DATA_DIR"] = str(_TEST_DATA_DIR)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def api():
    # Entering the context manager triggers the startup event that seeds the
    # database (tiers, accounts, settings).
    with TestClient(app) as client:
        yield client
