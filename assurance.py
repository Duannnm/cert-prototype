"""Demonstration of downstream clearance checking and portable oversight evidence."""
import io
import json
import secrets
import zipfile

import db
import rules as R
import services as S


@S.transactional
@S.permitted("issue_clearance")
def issue_clearance(conn, actor, now, case_id, action):
    if actor.role not in (R.INVESTIGATOR, R.LEGAL_REVIEWER, R.LEGAL_LEAD):
        return S.Outcome(False, "This role cannot request a clearance")
    if action not in R.RELIANCE_ACTIONS:
        return S.Outcome(False, "Unknown reliance action")
    case = S.get_case(conn, case_id)
    gate = S.case_gate(conn, case_id)
    if gate.state != R.CLEAR:
        S._record_attempt(conn, actor, now, case_id, action, "clearance_issue", "Blocked", gate.reasons)
        return S.Outcome(False, "Clearance refused: reliance is not CLEAR", gate.reasons)
    review = S.latest_review(conn, case_id)
    reference = "CLR-" + secrets.token_hex(12).upper()
    payload = {"reference": reference, "case_id": case_id, "action": action,
               "evidence_version": case["evidence_version"], "review_id": review["review_id"],
               "issued_on": S.ts(now), "issued_by": actor.user_id}
    S._log(conn, actor, now, "Clearance issued", reference, case_id, after=payload)
    return S.Outcome(True, "Clearance issued for this action and evidence version", data=payload)


@S.transactional
@S.permitted("verify_clearance")
def verify_clearance(conn, actor, now, case_id, action, reference):
    """Recheck authoritative live state. This never executes an actual recovery action."""
    case = S.get_case(conn, case_id)
    row = conn.execute("SELECT * FROM audit_log WHERE action = 'Clearance issued' AND object = ?",
                       (reference.strip(),)).fetchone()
    problems = []
    payload = db.from_json(row["after"], {}) if row else {}
    if not row:
        problems.append("No issued clearance matches this reference")
    else:
        if payload["case_id"] != case_id:
            problems.append("Clearance belongs to a different case")
        if payload["action"] != action:
            problems.append("Clearance does not permit this action")
        if payload["evidence_version"] != case["evidence_version"]:
            problems.append("Evidence changed after clearance: a fresh review and clearance are required")
        review = S.latest_review(conn, case_id)
        if not review or review["review_id"] != payload["review_id"]:
            problems.append("The independent review has changed since clearance")
    if action not in R.RELIANCE_ACTIONS:
        problems.append("Unknown reliance action")
    gate = S.case_gate(conn, case_id)
    if gate.state != R.CLEAR:
        problems += gate.reasons or ["The case is not open for reliance"]
    allowed = not problems
    S._record_attempt(conn, actor, now, case_id, action, "clearance_verification",
                      "Permitted" if allowed else "Blocked", problems or ["Current clearance verified"])
    S._log(conn, actor, now, "Downstream clearance verification", reference.strip(), case_id,
           after={"action": action, "permitted": allowed, "reasons": problems,
                  "simulation": True, "evidence_version": case["evidence_version"]})
    return S.Outcome(allowed, "SIMULATION: action may proceed" if allowed else "SIMULATION: action refused",
                     problems, {"clearance": payload, "gate_state": gate.state})


@S.transactional
@S.permitted("oversight_export")
def oversight_export(conn, actor, now):
    if actor.role not in (R.AUDIT, R.LEGAL_LEAD):
        return S.Outcome(False, "Switch to Internal audit or Legal lead to prepare an oversight export")
    S._log(conn, actor, now, "Oversight evidence package prepared", "oversight-export",
           after={"scope": "All registered synthetic cases", "external_transmission": False})
    # The audit write starts the transaction before any snapshot reads.
    tables = ("cases", "tasks", "reviews", "exceptions", "gate_attempts", "defect_links", "audit_log")
    files = {name + ".json": db.canonical_json([dict(r) for r in conn.execute(
        f"SELECT * FROM {name} ORDER BY rowid")]) for name in tables}
    files["source_fingerprints.json"] = db.canonical_json(db.verify_source_records(conn))
    files["integrity.json"] = db.canonical_json(db.verify_audit_chain(conn))
    manifest = {"format_version": 1, "demo_time": S.ts(now), "exported_at_utc": db.utc_now(),
                "prepared_by": actor.user_id, "scope": "All registered synthetic cases",
                "case_count": len(S.list_cases(conn)),
                "audit_head": conn.execute("SELECT entry_hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()[0],
                "limitations": ["Synthetic data; role switching is not authentication",
                    "No transmission to an external authority occurs",
                    "Hashes detect later changes only if a trusted copy is independently retained",
                    "Not digitally signed; not independently anchored",
                    "Omitted cases require reconciliation against separate legal and recovery registers"],
                "sha256": {name: db.sha256_of(content) for name, content in files.items()}}
    files["manifest.json"] = db.canonical_json(manifest)
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return S.Outcome(True, "Oversight evidence package prepared", data={"bytes": target.getvalue(),
                                                                      "manifest": manifest})
