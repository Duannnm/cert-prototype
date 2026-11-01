import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db  # noqa: E402
import seed  # noqa: E402
import services as S  # noqa: E402

NOW = datetime(2013, 11, 18, 10, 0)


@pytest.fixture
def conn(tmp_path):
    """A fresh copy of the full synthetic seed, at the demo date."""
    path = seed.build(tmp_path / "cert.db")
    c = db.connect(path)
    yield c
    c.close()


@pytest.fixture
def actor(conn):
    return lambda user_id: S.get_actor(conn, user_id)


@pytest.fixture
def observe(request):
    """Record what a test observed, so evaluation.py can report it in test_results.md."""
    def _observe(text: str) -> None:
        request.node.user_properties.append(("observed", text))
    return _observe
