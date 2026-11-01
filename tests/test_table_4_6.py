"""One test per row of report Table 4.6 (test conditions and expected outcomes)."""
from datetime import date

import rules as R
import seed
import services as S
from conftest import NOW

C014 = dict(case_id="C014", branch="214", disputed_start="2013-04-01", disputed_end="2013-05-12",
            horizon_version="Horizon Online v2", status="active")


def test_01_relevant_defect_with_overlapping_affected_period(conn, observe):
    """Relevant defect with overlapping affected period -> link flagged; documented inquiry required."""
    link = R.match_defect(C014, seed.DEFECTS["KEL-D01"])
    assert link.result == R.LINKED
    assert link.matched_fields == ("branch", "affected period", "version")
    assert "reported on 9 Sep 2013, after the disputed period" in link.explanation
    assert "does not establish causation" in link.explanation

    stored = [l for l in S.case_links(conn, "C014") if l["defect_id"] == "KEL-D01"][0]
    inquiry = [t for t in S.case_tasks(conn, "C014") if t["type"] == "Defect inquiry"][0]
    assert stored["result"] == R.LINKED and inquiry["defect_id"] == "KEL-D01" and inquiry["required"] == 1

    # A newly flagged link on an active case opens a required inquiry that blocks the gate.
    S.load_defect(conn, S.get_actor(conn, "u_okafor"), NOW, seed.SAMPLE_LATER_DEFECT)
    new = [t for t in S.case_tasks(conn, "C014", open_only=True) if t["type"] == "Defect inquiry"]
    assert len(new) == 1 and new[0]["defect_id"] == "KEL-D07"
    gate = S.case_gate(conn, "C014")
    assert gate.blocked and any(new[0]["task_id"] in r for r in gate.reasons)
    observe(f"C014 ↔ KEL-D01 Linked on branch, affected period and version although reported months later; "
            f"inquiry {inquiry['task_id']} assigned to the investigator. Loading KEL-D07 opened required "
            f"inquiry {new[0]['task_id']}, which the gate lists as a blocker.")


def test_02_unrelated_branch_or_incompatible_version(conn, observe):
    """Unrelated branch or incompatible version -> no automatic link; explained manual assessment possible."""
    version = R.match_defect(C014, seed.DEFECTS["KEL-D02"])
    assert version.result == R.NO_MATCH and version.failed_fields == ("version",)
    assert "different Horizon version" in version.explanation
    assert "manual assessment remains possible" in version.explanation

    branch = R.match_defect({**C014, "branch": "117"}, seed.DEFECTS["KEL-D01"])
    assert branch.result == R.NO_MATCH and branch.failed_fields == ("branch",)
    assert "outside the defect's scope" in branch.explanation

    assert not any(t["defect_id"] == "KEL-D02" for t in S.case_tasks(conn, "C014"))
    search = [i for i in S.evidence_items(conn, "C001") if i["item_type"] == R.DEFECT_SEARCH][0]
    assert search["reason"].startswith(R.NO_KNOWN_DEFECT)
    for link in S.case_links(conn, "C001"):
        assert "reliable" not in link["explanation"].lower()
    observe("C014 ↔ KEL-D02: No automatic link — “different Horizon version (defect affects Legacy Horizon; "
            "case recorded on Horizon Online v2)”; no task created. Branch 117 vs KEL-D01: outside scope. "
            f"C001 reported as “{R.NO_KNOWN_DEFECT}”, never as reliable.")


def test_03_missing_audit_period_or_unknown_field(conn, observe):
    """Missing audit period or unknown field -> gap or uncertainty shown; follow-up task assigned."""
    partial = R.assess_supplier_item(R.ARQ, "2013-04-01", "2013-05-12", [
        {"period_start": "2013-04-01", "period_end": "2013-04-28", "availability": R.DELIVERED}])
    assert partial.status == R.GAP
    assert partial.reason.startswith("4 of 6 weeks received; missing 29 Apr – 12 May 2013")

    arq = [i for i in S.evidence_items(conn, "C014") if i["item_type"] == R.ARQ][0]
    task = S._open_task(conn, "C014", "Evidence retrieval", R.ARQ)
    assert arq["status"] == R.GAP and task["owner_role"] == R.SUPPLIER_LIAISON
    assert "29 Apr – 12 May 2013" in task["title"]

    unknown = [l for l in S.case_links(conn, "C008") if l["defect_id"] == "KEL-D01"][0]
    manual = S._open_task(conn, "C008", "Manual review")
    search = [i for i in S.evidence_items(conn, "C008") if i["item_type"] == R.DEFECT_SEARCH][0]
    assert unknown["result"] == R.MANUAL_REVIEW and search["status"] == R.UNKNOWN
    assert manual["owner_role"] == R.INVESTIGATOR

    logs = [i for i in S.evidence_items(conn, "C007") if i["item_type"] == R.REMOTE_LOGS][0]
    assert logs["status"] == R.UNKNOWN and S._open_task(conn, "C007", "Evidence retrieval", R.REMOTE_LOGS)
    observe(f"C014 ARQ shown as Gap (“{arq['reason']}”); retrieval {task['task_id']} assigned to M. Okafor "
            f"(supplier liaison). C008 version Unknown → manual-review queue ({manual['task_id']}), defect search "
            "Unknown. C007 remote-intervention logs Unknown with a confirmation task.")


def test_04_defect_learned_after_a_decision(conn, observe):
    """Defect learned after a decision -> reassessment tasks for closed and earlier cases."""
    before = {r["review_id"]: dict(r) for r in conn.execute("SELECT * FROM reviews")}
    out = S.load_defect(conn, S.get_actor(conn, "u_okafor"), NOW, seed.SAMPLE_LATER_DEFECT)
    assert out.ok and out.data["cases_screened"] == 10 and out.data["reassessment_tasks"] == 2

    tasks = {t["case_id"]: t for t in S.case_tasks(conn, open_only=True)
             if t["type"] == "Reassessment" and t["defect_id"] == "KEL-D07"}
    assert set(tasks) == {"C011", "C014"}
    assert S.get_case(conn, "C011")["status"] == "closed"
    for cid, t in tasks.items():
        original = S.latest_review(conn, cid)
        assert t["linked_to"] == original["review_id"]
        assert original["decision"] in t["detail"] and original["reasons"] in t["detail"]
    after = {r["review_id"]: dict(r) for r in conn.execute("SELECT * FROM reviews")}
    assert after == before  # original decisions preserved, not overwritten

    legacy = [t for t in S.case_tasks(conn, "C003") if t["type"] == "Reassessment"][0]
    assert legacy["defect_id"] == "KEL-D05"  # 2008 case screened regardless of date
    observe(f"{out.message} Tasks {tasks['C011']['task_id']} (closed C011) and {tasks['C014']['task_id']} "
            f"(C014) link to original decisions {tasks['C011']['linked_to']} and {tasks['C014']['linked_to']}, "
            "which are unchanged. Seeded KEL-D05 caught closed 2008 Legacy Horizon case C003.")


def test_05_self_approval_or_open_inquiry_at_gate(conn, actor, observe):
    """Self-approval or open inquiry at reliance gate -> approval blocked and reason recorded."""
    reviews = conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
    self_review = S.record_review(conn, actor("u_shah"), NOW, "C005", declared_no_involvement=True,
                                  decision=R.RELY, reasons="Evidence complete.")
    assert not self_review.ok and self_review.data["self_review"]
    assert any("Self-approval blocked: R. Shah" in p for p in self_review.problems)

    open_inquiry = S.record_review(conn, actor("u_wong"), NOW, "C014", declared_no_involvement=True,
                                   decision=R.RELY, reasons="Proceed.")
    assert not open_inquiry.ok and any("ARQ audit data — Gap" in p for p in open_inquiry.problems)

    reliance = S.attempt_reliance(conn, actor("u_tan"), NOW, "C014", R.RELIANCE_ACTIONS[0])
    assert not reliance.ok
    assert conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == reviews

    logged = S.gate_attempts(conn)[-3:]
    assert [a["outcome"] for a in logged] == ["Blocked"] * 3
    assert logged[0]["category"] == "self_review" and logged[0]["reasons"]

    allowed = S.record_review(conn, actor("u_wong"), NOW, "C005", declared_no_involvement=True,
                              decision=R.RELY, reasons="Complete ARQ and remote-intervention data reconcile.")
    assert allowed.ok and S.case_gate(conn, "C005").state == R.CLEAR
    observe("R. Shah (involved investigator) self-approval on C005 blocked and logged as a self-review attempt. "
            "“Reliance may proceed” on C014 by uninvolved K. Wong blocked while the ARQ gap and expert "
            "correction are open; recovery demand on C014 blocked. Control: K. Wong's review of C005 was "
            "accepted and the gate turned CLEAR.")


def test_06_overdue_request_or_imminent_deadline(conn, observe):
    """Overdue request or imminent deadline -> correct routine or immediate escalation generated."""
    today = seed.DEMO_DATE
    nine, ten = date(2013, 11, 5), date(2013, 11, 4)
    nineteen, twenty = date(2013, 10, 22), date(2013, 10, 21)
    assert R.working_days_between(ten, today) == 10 and R.working_days_between(twenty, today) == 20
    assert R.assess_escalation(nine, today).level == R.ESC_NONE
    assert R.assess_escalation(ten, today).level == R.ESC_LEGAL_LEAD
    assert R.assess_escalation(nineteen, today).level == R.ESC_LEGAL_LEAD
    assert R.assess_escalation(twenty, today).level == R.ESC_COMMITTEE
    assert R.assess_escalation(today, today, legal_deadline=date(2013, 11, 25)).level == R.ESC_IMMEDIATE
    assert R.assess_escalation(today, today, legal_deadline=date(2013, 11, 26)).level == R.ESC_NONE
    assert R.assess_escalation(today, today, urgent=True).level == R.ESC_IMMEDIATE

    esc = {e["task_id"]: e for e in S.open_escalations(conn, today)}
    by_case = {(e["case_id"], e["type"]): e["level"] for e in esc.values()}
    assert by_case[("C006", "Evidence retrieval")] == R.ESC_COMMITTEE
    assert by_case[("C014", "Evidence retrieval")] == R.ESC_LEGAL_LEAD
    assert by_case[("C007", "Evidence retrieval")] == R.ESC_IMMEDIATE
    logged = [e for e in S.audit_entries(conn) if e["action"].startswith("Rule 4 escalation")]
    assert logged
    observe("Boundaries: 9 WD none, 10 WD → legal lead, 20 WD → Committee, deadline 5 WD away → immediate, "
            "6 WD away → none. Seed at 18 Nov 2013: C006 ARQ request (25 WD) → Committee; C014 ARQ request "
            "(17 WD) → legal lead; C007 deadline 21 Nov (3 WD) → immediate. "
            f"{len(logged)} escalations logged.")


def test_07_expert_statement_omits_relevant_known_defect(conn, actor, observe):
    """Expert statement omits a relevant known defect -> omission recorded; correction required; gate blocked."""
    assert R.expert_completeness(["KEL-D02"], ["KEL-D01"]) == ["KEL-D01"]
    check = S.expert_checks(conn, "C014")[-1]
    correction = S._open_task(conn, "C014", "Expert correction")
    assert check["omissions"] == ["KEL-D01"] and check["correction_status"] == "Correction requested"
    assert correction is not None and correction["required"] == 1
    gate = S.case_gate(conn, "C014")
    assert gate.blocked and any("omits KEL-D01" in r for r in gate.reasons)

    S.record_expert_statement(conn, actor("u_patel"), NOW, case_id="C014", statement_id="ES-014",
                              author="Dr P. Grant", defects_addressed=["KEL-D01", "KEL-D02"])
    S.run_expert_check(conn, actor("u_patel"), NOW, "C014")
    assert S._open_task(conn, "C014", "Expert correction") is None
    still = S.case_gate(conn, "C014")
    assert still.blocked and not any("omits" in r for r in still.reasons)
    observe(f"Check {check['check_id']} recorded omission of KEL-D01 in ES-014 v1 and opened "
            f"{correction['task_id']}; gate blocked with the omission as a reason. After v2 addressed KEL-D01 "
            "the correction closed, but the gate stayed blocked on the ARQ gap and the review decision.")


def test_08_unavailable_evidence_after_reasonable_retrieval(conn, actor, observe):
    """Unavailable evidence after reasonable retrieval -> gap retained; reasons and separate authorisation."""
    arq = [i for i in S.evidence_items(conn, "C009") if i["item_type"] == R.ARQ][0]
    gate = S.case_gate(conn, "C009")
    ex = S.case_exceptions(conn, "C009")[0]
    assert arq["status"] == R.GAP  # never marked complete
    assert gate.state == R.CLEAR and any("remains visible" in n for n in gate.notes)
    assert ex["status"] == "Authorised" and ex["authoriser"] != ex["proposed_by"]
    assert S.latest_review(conn, "C009")["exception_flag"] == 1

    missing_reasons = R.exception_proposal_problems(
        proposer_id="u_lim", proposer_name="J. Lim", proposer_role=R.LEGAL_REVIEWER, involved_users=[],
        item_type=R.ARQ, item_status=R.GAP, retrieval_exhausted=True, open_required=[],
        implications="", proposed_action="", reasons="", duties_confirmed=False)
    assert len(missing_reasons) == 2

    assert S.case_gate(conn, "C010").blocked  # proposed but not yet authorised
    out = S.authorise_exception(conn, actor("u_clarke"), NOW, "EX-002", independence_confirmed=True)
    assert out.ok
    arq10 = [i for i in S.evidence_items(conn, "C010") if i["item_type"] == R.ARQ][0]
    assert arq10["status"] == R.GAP
    assert S.case_gate(conn, "C010").reasons == [
        "No independent review recorded: a reviewer with no prior involvement must record a reasoned decision"]
    observe("C009 ARQ stays “Gap” after retrieval was documented as exhausted; EX-001 proposed by J. Lim and "
            "separately authorised by D. Morgan; gate CLEAR only under the exception, gap still shown. A proposal "
            "without implications, action, reasons or duty confirmation is rejected. EX-002 authorised by "
            "external reviewer E. Clarke leaves the C010 gap visible and still requires a review.")


def test_09_exception_with_open_inquiry_or_conflicted_authoriser(conn, actor, observe):
    """Exception attempted with an open inquiry or conflicted authoriser -> rejected, recorded and escalated."""
    seeded = [a for a in S.gate_attempts(conn) if a["category"].startswith("exception")]
    assert {(a["case_id"], a["outcome"]) for a in seeded} == {("C006", "Blocked"), ("C010", "Blocked")}
    c010 = [a for a in seeded if a["case_id"] == "C010"][0]
    assert any("Conflicted authoriser: D. Morgan" in r for r in c010["reasons"])
    esc = {t["case_id"]: t for t in S.case_tasks(conn) if t["type"] == "Escalation" and t["status"] == "Open"}
    assert esc["C010"]["escalate_to"] == R.TO_COMMITTEE and esc["C006"]["escalate_to"] == R.TO_LEGAL_LEAD

    out = S.propose_exception(conn, actor("u_lim"), NOW, "C014", item_type=R.ARQ,
                              implications="Two weeks untested.", proposed_action="Proceed on four weeks.",
                              reasons="Supplier delay.", duties_confirmed=True)
    assert not out.ok and any("cannot bypass an open required inquiry" in p for p in out.problems)
    assert S.gate_attempts(conn, "C014")[-1]["category"] == "exception_proposal"
    assert S._open_task(conn, "C014", "Escalation")["urgent"] == 1

    own = R.exception_authorisation_problems(
        authoriser_id="u_wong", authoriser_name="K. Wong", authoriser_role=R.LEGAL_REVIEWER,
        authoriser_external=False, proposer_id="u_wong", involved_users=[], open_required=[],
        independence_confirmed=True)
    assert any("separate from the person who proposed" in p for p in own)
    observe("Seeded: K. Wong's C006 proposal (retrieval still open) rejected and escalated to the legal lead; "
            "D. Morgan's C010 authorisation rejected as conflicted and escalated to the Audit & Risk Committee. "
            "Live: J. Lim's C014 proposal rejected (open ARQ request), logged and escalated. A proposer "
            "authorising their own exception is rejected.")
