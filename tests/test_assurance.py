import io
import json
import zipfile

import assurance as A
import db
import rules as R
import seed
import services as S
from conftest import NOW
from test_pages import app


def test_clearance_requires_clear_gate_and_authorised_role(conn, actor):
    assert not A.issue_clearance(conn, actor("u_tan"), NOW, "C014", R.RELIANCE_ACTIONS[0]).ok
    assert not A.issue_clearance(conn, actor("u_okafor"), NOW, "C001", R.RELIANCE_ACTIONS[0]).ok
    assert not A.issue_clearance(conn, actor("u_tan"), NOW, "C001", "unknown").ok


def test_clearance_checks_case_action_and_reference(conn, actor):
    out = A.issue_clearance(conn, actor("u_tan"), NOW, "C001", R.RELIANCE_ACTIONS[0])
    assert out.ok
    reference = out.data["reference"]
    assert A.verify_clearance(conn, actor("u_tan"), NOW, "C001", R.RELIANCE_ACTIONS[0], reference).ok
    assert not A.verify_clearance(conn, actor("u_tan"), NOW, "C001", R.RELIANCE_ACTIONS[1], reference).ok
    assert not A.verify_clearance(conn, actor("u_tan"), NOW, "C014", R.RELIANCE_ACTIONS[0], reference).ok
    assert not A.verify_clearance(conn, actor("u_tan"), NOW, "C001", R.RELIANCE_ACTIONS[0], "fabricated").ok
    assert db.verify_audit_chain(conn)["ok"]


def test_later_evidence_invalidates_clearance(conn, actor):
    out = A.issue_clearance(conn, actor("u_tan"), NOW, "C001", R.RELIANCE_ACTIONS[0])
    case = S.get_case(conn, "C001")
    defect = {**seed.SAMPLE_LATER_DEFECT, "defect_id": "KEL-NEW", "affected_branches": case["branch"],
              "affected_start": case["disputed_start"], "affected_end": case["disputed_end"],
              "versions": case["horizon_version"]}
    assert S.load_defect(conn, actor("u_okafor"), NOW, defect).ok
    check = A.verify_clearance(conn, actor("u_tan"), NOW, "C001", R.RELIANCE_ACTIONS[0], out.data["reference"])
    assert not check.ok
    assert any("Evidence changed" in reason for reason in check.problems)


def test_new_review_invalidates_old_clearance(conn, actor):
    out = A.issue_clearance(conn, actor("u_tan"), NOW, "C001", R.RELIANCE_ACTIONS[0])
    assert S.record_review(conn, actor("u_wong"), NOW, "C001", declared_no_involvement=True,
                           decision=R.HOLD, reasons="Further independent inquiry required").ok
    assert not A.verify_clearance(conn, actor("u_tan"), NOW, "C001", R.RELIANCE_ACTIONS[0], out.data["reference"]).ok


def test_oversight_export_permissions_and_fingerprints(conn, actor):
    assert not A.oversight_export(conn, actor("u_tan"), NOW).ok
    A.verify_clearance(conn, actor("u_tan"), NOW, "C014", R.RELIANCE_ACTIONS[0], "fabricated")
    result = A.oversight_export(conn, actor("u_ng"), NOW)
    assert result.ok
    with zipfile.ZipFile(io.BytesIO(result.data["bytes"])) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        for name, fingerprint in manifest["sha256"].items():
            assert db.sha256_of(archive.read(name).decode()) == fingerprint
        assert json.loads(archive.read("integrity.json"))["ok"]
        assert any(r["category"] == "clearance_verification" for r in json.loads(archive.read("gate_attempts.json")))
        assert len(json.loads(archive.read("cases.json"))) == 10


def test_clearance_page_rejects_c014_and_accepts_c001(app):
    app.switch_page("views/clearance.py").run()
    next(b for b in app.button if b.label == "Request clearance from CERT").click().run()
    assert any("refused" in e.value for e in app.error)
    next(s for s in app.selectbox if s.label == "Case to verify").select("C001").run()
    next(b for b in app.button if b.label == "Request clearance from CERT").click().run()
    next(b for b in app.button if b.label == "Verify before proceeding").click().run()
    assert not app.exception
    assert any("action may proceed" in s.value for s in app.success)


def test_oversight_page_prepares_snapshot_for_auditor(app):
    app.selectbox(key="role").select(R.AUDIT).run()
    app.switch_page("views/oversight_export.py").run()
    next(b for b in app.button if b.label == "Prepare oversight package").click().run()
    assert not app.exception
    assert any("10 registered cases" in s.value for s in app.success)
