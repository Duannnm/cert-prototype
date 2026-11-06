"""Saved evidence and navigation checks for the presentation workflow."""
import report_data
import rules as R
from test_pages import app


def test_saved_report_metrics_and_scenarios():
    report = report_data.REPORT_PATH.read_text(encoding="utf-8")
    sections = report_data.report_sections(report)
    metrics = report_data.table_rows(sections["Effectiveness metrics"])
    assert len(metrics) >= 4
    assert all(len(row) == 4 for row in metrics)
    scenarios = next(v for k, v in sections.items() if k.startswith("Table 4.6"))
    assert len(report_data.table_rows(scenarios)) == 9


def test_missing_report_explains_refresh(app, monkeypatch, tmp_path):
    monkeypatch.setattr(report_data, "REPORT_PATH", tmp_path / "missing.md")
    app.switch_page("views/test_results.py").run()
    assert not app.exception
    assert any("No evaluation report" in w.value for w in app.warning)


def test_case_deep_link_selects_reliance_tab(app):
    app.query_params["case"] = "C014"
    app.query_params["tab"] = "reliance"
    app.switch_page("views/case_view.py").run()
    assert not app.exception
    assert app.session_state["case_tabs"] == "Reliance & exceptions"


def test_results_page_shows_saved_evidence(app):
    app.switch_page("views/test_results.py").run()
    assert not app.exception
    assert len(app.metric) == 4
    assert all(m.value != "Not reported" for m in app.metric)
    assert any("Generated" in c.value for c in app.caption)


def test_loading_later_defect_reports_two_reassessments(app):
    app.selectbox(key="role").select(R.SUPPLIER_LIAISON).run()
    app.switch_page("views/defects.py").run()
    next(b for b in app.button if b.label == "Load KEL-D07 and run Rule 5").click().run()
    assert not app.exception
    assert {m.label: m.value for m in app.metric} == {
        "Cases screened": "10", "Cases flagged for inquiry": "2", "Reassessments created": "2"}
    links = app.get("link_button")
    assert any("case=C011" in link.proto.url for link in links)
