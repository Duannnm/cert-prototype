"""Role separation, case scope and independent reassessment controls."""
import pytest

import access
import assurance
import db
import rules as R
import seed
import services as S
from conftest import NOW
from test_pages import app


@pytest.mark.parametrize("uid", ["u_ng", "u_chen", "u_evans", "u_okafor", "u_patel"])
def test_non_operational_roles_cannot_perform_reliance(conn, actor, uid):
    assert not S.attempt_reliance(conn, actor(uid), NOW, "C001", R.RELIANCE_ACTIONS[0]).ok
    assert not assurance.issue_clearance(conn, actor(uid), NOW, "C001", R.RELIANCE_ACTIONS[0]).ok
    assert not assurance.verify_clearance(conn, actor(uid), NOW, "C001", R.RELIANCE_ACTIONS[0], "fake").ok


def test_unassigned_investigator_cannot_act_on_another_case(conn, actor):
    assert not S.can_access_case(conn, actor("u_shah"), "C014")
    assert S.can_access_case(conn, actor("u_tan"), "C014")
    assert not S.attempt_reliance(conn, actor("u_shah"), NOW, "C014", R.RELIANCE_ACTIONS[0]).ok


def test_upload_permission_is_enforced_without_ui(conn, actor):
    for uid in ("u_tan", "u_ng", "u_chen", "u_evans", "u_lim"):
        assert not S.load_defect(conn, actor(uid), NOW, seed.SAMPLE_LATER_DEFECT).ok
    assert S.get_defect(conn, "KEL-D07") is None
    assert S.load_defect(conn, actor("u_okafor"), NOW, seed.SAMPLE_LATER_DEFECT).ok


def test_external_overseer_has_read_only_navigation(app):
    app.selectbox(key="role").select(R.OVERSEER).run()
    assert not app.exception
    assert access.page_allowed(S.Actor("u_evans", "P. Evans", R.OVERSEER), "dashboard")
    assert not access.page_allowed(S.Actor("u_evans", "P. Evans", R.OVERSEER), "defects")
    app.switch_page("views/case_view.py").run()
    assert not app.exception
    assert not any(b.label in ("Record review", "Issue recovery demand", "Record outcome", "Assign reviewer") for b in app.button)


def reassess_task(conn, cid):
    return next(t for t in S.case_tasks(conn, cid, open_only=True)
                if t["type"] == "Reassessment" and t["defect_id"] == "KEL-D07")


def test_reassessment_requires_assigned_different_reviewer(conn, actor):
    S.load_defect(conn, actor("u_okafor"), NOW, seed.SAMPLE_LATER_DEFECT)
    task = reassess_task(conn, "C011")
    original = S.latest_review(conn, "C011")
    assert task["owner"] != original["reviewer"]
    denied = S.complete_reassessment(conn, actor(original["reviewer"]), NOW, task["task_id"],
                                    outcome=S.REASSESS_REFER, reasons="Material needs independent assessment", declared_no_involvement=True)
    assert not denied.ok
    assert not S.assign_reassessment(conn, actor("u_morgan"), NOW, task["task_id"], original["reviewer"]).ok
    conn.execute("UPDATE tasks SET owner = ? WHERE task_id = ?", (original["reviewer"], task["task_id"]))
    denied = S.complete_reassessment(conn, actor(original["reviewer"]), NOW, task["task_id"],
                                    outcome=S.REASSESS_REFER, reasons="Old assignment must not bypass independence", declared_no_involvement=True)
    assert not denied.ok and any("original reviewer" in reason for reason in denied.problems)


def test_no_referral_requires_resolved_inquiry_but_referral_can_preserve_uncertainty(conn, actor):
    S.load_defect(conn, actor("u_okafor"), NOW, seed.SAMPLE_LATER_DEFECT)
    task = reassess_task(conn, "C011")
    reviewer = actor(task["owner"])
    original = dict(S.latest_review(conn, "C011"))
    assert not S.complete_reassessment(conn, reviewer, NOW, task["task_id"], outcome=S.REASSESS_NO_REFERRAL,
                                       reasons="No change is required", declared_no_involvement=True).ok
    assert S.complete_reassessment(conn, reviewer, NOW, task["task_id"], outcome=S.REASSESS_REFER,
                                   reasons="Unresolved defect may undermine the earlier decision", declared_no_involvement=True).ok
    assert S.latest_review(conn, "C011") == original
    assert S.case_gate(conn, "C011").blocked
    follow = next(t for t in S.case_tasks(conn, "C011", open_only=True) if t["type"] == "Referral follow-up")
    assert not S.record_referral_followup(conn, actor("u_evans"), NOW, follow["task_id"], "Received by authority; reference 123").ok
    assert S.record_referral_followup(conn, actor(follow["owner"]), NOW, follow["task_id"],
                                      "Received by prosecutor; reference REF-123; further inquiry requested").ok
    assert S.case_gate(conn, "C011").blocked  # The outstanding inquiry still requires work.


def test_no_referral_can_complete_after_documented_inquiry(conn, actor):
    S.load_defect(conn, actor("u_okafor"), NOW, seed.SAMPLE_LATER_DEFECT)
    task = reassess_task(conn, "C011")
    inquiry = next(t for t in S.case_tasks(conn, "C011", open_only=True) if t["type"] == "Defect inquiry")
    assert S.record_inquiry_outcome(conn, actor("u_patel"), NOW, inquiry["task_id"], outcome=S.INQUIRY_NOT_RELEVANT,
                                    finding="Compared transactions and symptoms; the affected reversal did not occur").ok
    assert S.complete_reassessment(conn, actor(task["owner"]), NOW, task["task_id"], outcome=S.REASSESS_NO_REFERRAL,
                                   reasons="Independent assessment supports the documented technical exclusion", declared_no_involvement=True).ok


def test_role_upgrade_preserves_case_data_and_audit_chain(conn):
    conn.execute("UPDATE users SET role = ? WHERE user_id = 'u_ng'", ("Internal audit / Audit & Risk Committee",))
    conn.commit()
    before = S.list_cases(conn)
    S.configure_demo_roles(conn)
    S.configure_demo_roles(conn)
    assert S.get_actor(conn, "u_ng").role == R.AUDIT
    assert S.get_actor(conn, "u_evans").role == R.OVERSEER
    assert S.list_cases(conn) == before
    assert db.verify_audit_chain(conn)["ok"]


def test_pending_legacy_reassessment_receives_missing_inquiry_once(conn):
    # Simulate a pre-upgrade task created without a separate closed-case inquiry.
    task = next(t for t in S.case_tasks(conn, "C003", open_only=True) if t["type"] == "Defect inquiry")
    conn.execute("DELETE FROM tasks WHERE task_id = ?", (task["task_id"],))
    S.configure_demo_roles(conn)
    first = S.case_tasks(conn, "C003", open_only=True)
    S.configure_demo_roles(conn)
    assert S.case_tasks(conn, "C003", open_only=True) == first
    assert any(t["type"] == "Defect inquiry" for t in first)


def test_no_eligible_reviewer_escalates_instead_of_assigning_conflicted_user(conn, actor):
    reviewers = [u.user_id for u in S.list_users(conn) if u.role == R.LEGAL_REVIEWER]
    conn.execute("UPDATE cases SET involved_users = ? WHERE case_id = 'C011'", (db.to_json(reviewers),))
    S.load_defect(conn, actor("u_okafor"), NOW, seed.SAMPLE_LATER_DEFECT)
    assert reassess_task(conn, "C011")["owner"] == "system"
    assert any(t["type"] == "Escalation" and "no eligible reviewer" in t["title"]
               for t in S.case_tasks(conn, "C011", open_only=True))


def test_case_scoped_complaints_and_unknown_action_are_rejected(conn, actor):
    assert not S.load_complaints(conn, actor("u_shah"), NOW,
                                [{"branch": "214", "complaint_id": "NO-ACCESS"}], "test.csv").ok
    assert not S.attempt_reliance(conn, actor("u_tan"), NOW, "C001", "Unrecognised action").ok


def test_all_roles_render_case_view_without_exposing_illegal_actions(app):
    for role in R.ROLES:
        app.selectbox(key="role").select(role).run()
        app.switch_page("views/case_view.py").run()
        assert not app.exception, role
