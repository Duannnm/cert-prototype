"""Smoke test: every page, and the case view for every case, renders without an exception."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import db
import seed

ROOT = Path(__file__).resolve().parents[1]
PAGES = ["views/case_list.py", "views/case_view.py", "views/defects.py", "views/dashboard.py",
         "views/audit_log.py", "views/about.py", "views/demo.py", "views/test_results.py"]


@pytest.fixture
def app(tmp_path, monkeypatch):
    path = seed.build(tmp_path / "cert.db")
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", path)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    at.run()
    return at


@pytest.mark.parametrize("page", PAGES)
def test_page_renders(app, page):
    app.switch_page(page).run()
    assert not app.exception


@pytest.mark.parametrize("case_id", ["C001", "C003", "C005", "C006", "C007", "C008", "C009", "C010", "C011", "C014"])
def test_case_view_renders(app, case_id):
    app.session_state["case_id"] = case_id
    app.switch_page("views/case_view.py").run()
    assert not app.exception
    assert any(case_id in m.value for m in app.markdown)
