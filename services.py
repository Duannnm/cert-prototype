"""Workflow services: apply the rules in rules.py to the database in db.py.

Every user action goes through a function here so it is validated by the rules
engine, written atomically, and recorded in the append-only audit log. The
Streamlit pages and the seed script call these functions and nothing else
writes to the database.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import wraps

import db
import rules as R
import access
import inspect

SYSTEM = "CERT rules engine"
REQUIRED_TASK_TYPES = ("Evidence retrieval", "Defect inquiry", "Manual review",
                       "Expert correction", "Reassessment")
INQUIRY_RELEVANT = "Relevant – refer to independent reviewer"
INQUIRY_NOT_RELEVANT = "Not relevant – reasons recorded"
RETRIEVAL_UNAVAILABLE = "Unavailable after reasonable retrieval"
DEFECT_CSV_FIELDS = ("defect_id", "type", "affected_branches", "affected_start", "affected_end",
                     "versions", "symptoms", "date_reported")


@dataclass(frozen=True)
class Actor:
    user_id: str
    name: str
    role: str
    is_external: bool = False

    @property
    def label(self) -> str:
        return f"{self.name} – {self.role}"


@dataclass
class Outcome:
    ok: bool
    message: str
    problems: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)


SYSTEM_ACTOR = Actor("system", SYSTEM, "System")
REASSESS_REFER = "Refer earlier decision for review (prosecutor / appeal route)"
REASSESS_NO_REFERRAL = "No referral required – reasons recorded"


def transactional(fn):
    """Commit once at the outermost service call; roll back everything on error."""
    @wraps(fn)
    def wrapper(conn, *args, **kwargs):
        conn.tx_depth += 1
        try:
            result = fn(conn, *args, **kwargs)
            if conn.tx_depth == 1:
                conn.commit()
            return result
        except Exception:
            if conn.tx_depth == 1:
                conn.rollback()
            raise
        finally:
            conn.tx_depth -= 1
    return wrapper


# =============================================================================
# Reading helpers
# =============================================================================

def ts(now: datetime) -> str:
    return now.strftime("%Y-%m-%d %H:%M")


def permitted(operation):
    """Reject unauthorised mutations even when called outside the UI."""
    def decorate(fn):
        @wraps(fn)
        def guarded(conn, actor, now, *args, **kwargs):
            arguments = inspect.signature(fn).bind(conn, actor, now, *args, **kwargs).arguments
            problem = None
            permission = ("import_legacy_case" if operation == "register_case"
                          and arguments.get("data", {}).get("status") == "closed"
                          and actor.role == R.LEGAL_LEAD else operation)
            if not access.allows(actor, permission):
                problem = f"The role {actor.role} cannot perform {operation}"
            case_id = arguments.get("case_id")
            if not case_id and arguments.get("task_id"):
                row = conn.execute("SELECT case_id FROM tasks WHERE task_id = ?", (arguments["task_id"],)).fetchone()
                case_id = row[0] if row else None
            if case_id and not can_access_case(conn, actor, case_id):
                problem = "This investigator is not assigned to or involved in the case"
            if problem:
                _log(conn, actor, now, "Permission denied: " + operation, case_id=case_id, after={"reason": problem})
                return Outcome(False, "Action not permitted", [problem])
            return fn(conn, actor, now, *args, **kwargs)
        return guarded
    return decorate


def can_access_case(conn, actor, case_id):
    if actor.role not in R.ROLES:
        return False
    if actor.role != R.INVESTIGATOR:
        return True  # The demo's non-investigator scope is all registered synthetic cases.
    case = get_case(conn, case_id)
    return (case["registered_by"] == actor.user_id or actor.user_id in case["involved_users"]
            or any(t["owner"] == actor.user_id for t in case_tasks(conn, case_id)))


def visible_cases(conn, actor):
    return [c for c in list_cases(conn) if can_access_case(conn, actor, c["case_id"])]


@transactional
def configure_demo_roles(conn):
    """Upgrade existing demo databases without discarding casework."""
    changed = conn.execute("UPDATE users SET role = ? WHERE role = ?",
                           (R.AUDIT, "Internal audit / Audit & Risk Committee")).rowcount
    conn.execute("UPDATE tasks SET owner_role = ? WHERE owner_role = ?",
                 (R.AUDIT, "Internal audit / Audit & Risk Committee"))
    for uid, name, role, external in (("u_chen", "L. Chen", R.COMMITTEE, 0),
                                      ("u_evans", "P. Evans", R.OVERSEER, 1)):
        changed += conn.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?, ?)",
                                (uid, name, role, external, "Synthetic oversight identity")).rowcount
    if db.get_meta(conn, "role_policy_version") != "2":
        changed += conn.execute("UPDATE tasks SET owner = 'u_chen', owner_role = ? WHERE type = 'Escalation' "
                                "AND status = 'Open' AND escalate_to = ? AND owner_role = ?",
                                (R.COMMITTEE, R.TO_COMMITTEE, R.AUDIT)).rowcount
        for task in case_tasks(conn, open_only=True):
            if task["type"] != "Reassessment" or not task["defect_id"]:
                continue
            case = get_case(conn, task["case_id"])
            defect = get_defect(conn, task["defect_id"])
            link = next((l for l in case_links(conn, case["case_id"]) if l["defect_id"] == task["defect_id"]), None)
            existing = conn.execute("SELECT 1 FROM tasks WHERE case_id = ? AND defect_id = ? "
                                    "AND type IN ('Defect inquiry', 'Manual review') AND status = 'Open'",
                                    (case["case_id"], task["defect_id"])).fetchone()
            if defect and link and not (link["inquiry_status"] or "").startswith("Closed") and not existing:
                _create_inquiry_task(conn, datetime.strptime(task["created"], "%Y-%m-%d %H:%M"),
                                     case, defect, R.match_defect(case, defect))
                changed += 1
        db.set_meta(conn, "role_policy_version", "2")
    if changed:
        _log(conn, SYSTEM_ACTOR, datetime.now(), "Demo role configuration upgraded", after={"roles": list(R.ROLES)})


def get_actor(conn, user_id: str) -> Actor:
    if user_id == "system":
        return SYSTEM_ACTOR
    r = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return Actor(r["user_id"], r["name"], r["role"], bool(r["is_external"]))


def list_users(conn) -> list[Actor]:
    rows = conn.execute("SELECT * FROM users ORDER BY rowid").fetchall()
    return [Actor(r["user_id"], r["name"], r["role"], bool(r["is_external"])) for r in rows]


def user_name(conn, user_id: str | None) -> str:
    if not user_id:
        return ""
    if user_id == "system":
        return SYSTEM
    r = conn.execute("SELECT name FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return r["name"] if r else user_id


def _case_dict(row) -> dict:
    d = dict(row)
    d["involved_users"] = db.from_json(d["involved_users"], [])
    d["involvement_notes"] = db.from_json(d["involvement_notes"], {})
    return d


def get_case(conn, case_id: str) -> dict:
    row = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    if row is None:
        raise KeyError(case_id)
    return _case_dict(row)


def list_cases(conn) -> list[dict]:
    return [_case_dict(r) for r in conn.execute("SELECT * FROM cases ORDER BY case_id").fetchall()]


def _defect_dict(row) -> dict:
    d = dict(row)
    d["affected_branches"] = db.from_json(d["affected_branches"], R.UNKNOWN)
    d["versions"] = db.from_json(d["versions"], R.UNKNOWN)
    return d


def list_defects(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM defects ORDER BY loaded_on, defect_id").fetchall()
    return [_defect_dict(r) for r in rows]


def get_defect(conn, defect_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM defects WHERE defect_id = ?", (defect_id,)).fetchone()
    return _defect_dict(row) if row else None


def case_links(conn, case_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT l.*, d.type, d.symptoms, d.date_reported FROM defect_links l"
        " JOIN defects d ON d.defect_id = l.defect_id WHERE l.case_id = ?"
        " ORDER BY CASE l.result WHEN 'Linked' THEN 0 WHEN 'Manual review' THEN 1 ELSE 2 END,"
        " l.defect_id", (case_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["matched_fields"] = db.from_json(d["matched_fields"], [])
        out.append(d)
    return out


def case_tasks(conn, case_id: str | None = None, open_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM tasks WHERE 1=1"
    params: list = []
    if case_id:
        sql += " AND case_id = ?"
        params.append(case_id)
    if open_only:
        sql += " AND status = 'Open'"
    sql += " ORDER BY created, task_id"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def case_deliveries(conn, case_id: str, item_type: str | None = None) -> list[dict]:
    sql, params = "SELECT * FROM supplier_deliveries WHERE case_id = ?", [case_id]
    if item_type:
        sql += " AND item_type = ?"
        params.append(item_type)
    return [dict(r) for r in conn.execute(sql + " ORDER BY received_on, delivery_id", params).fetchall()]


def latest_statement(conn, case_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM expert_statements WHERE case_id = ? ORDER BY version DESC LIMIT 1",
                       (case_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["linked_defects"] = db.from_json(d["linked_defects"], [])
    return d


def statements(conn, case_id: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM expert_statements WHERE case_id = ? ORDER BY version",
                        (case_id,)).fetchall()
    return [{**dict(r), "linked_defects": db.from_json(r["linked_defects"], [])} for r in rows]


def latest_check(conn, statement: dict | None) -> dict | None:
    if statement is None:
        return None
    row = conn.execute(
        "SELECT * FROM expert_checks WHERE statement_id = ? AND statement_version = ?"
        " ORDER BY check_id DESC LIMIT 1", (statement["statement_id"], statement["version"])).fetchone()
    if not row:
        return None
    d = dict(row)
    d["relevant_defects"] = db.from_json(d["relevant_defects"], [])
    d["omissions"] = db.from_json(d["omissions"], [])
    return d


def expert_checks(conn, case_id: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM expert_checks WHERE case_id = ? ORDER BY check_id",
                        (case_id,)).fetchall()
    return [{**dict(r), "relevant_defects": db.from_json(r["relevant_defects"], []),
             "omissions": db.from_json(r["omissions"], [])} for r in rows]


def case_reviews(conn, case_id: str) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM reviews WHERE case_id = ? ORDER BY recorded_on, review_id", (case_id,)).fetchall()]


def latest_review(conn, case_id: str, include_historical: bool = True) -> dict | None:
    sql = "SELECT * FROM reviews WHERE case_id = ?"
    if not include_historical:
        sql += " AND is_historical = 0"
    row = conn.execute(sql + " ORDER BY recorded_on DESC, review_id DESC LIMIT 1", (case_id,)).fetchone()
    return dict(row) if row else None


def case_exceptions(conn, case_id: str | None = None) -> list[dict]:
    sql, params = "SELECT * FROM exceptions", []
    if case_id:
        sql += " WHERE case_id = ?"
        params.append(case_id)
    return [dict(r) for r in conn.execute(sql + " ORDER BY exception_id", params).fetchall()]


def evidence_items(conn, case_id: str) -> list[dict]:
    order = {t: i for i, t in enumerate(R.EVIDENCE_ITEMS)}
    rows = [dict(r) for r in conn.execute("SELECT * FROM evidence_items WHERE case_id = ?", (case_id,))]
    return sorted(rows, key=lambda r: order.get(r["item_type"], 99))


def branch_complaints(conn, branch: str) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM complaints WHERE branch = ? ORDER BY date", (branch,)).fetchall()]


def gate_attempts(conn, case_id: str | None = None) -> list[dict]:
    sql, params = "SELECT * FROM gate_attempts", []
    if case_id:
        sql += " WHERE case_id = ?"
        params.append(case_id)
    rows = conn.execute(sql + " ORDER BY ts, attempt_id", params).fetchall()
    return [{**dict(r), "reasons": db.from_json(r["reasons"], [])} for r in rows]


def audit_entries(conn, case_id: str | None = None) -> list[dict]:
    sql, params = "SELECT * FROM audit_log", []
    if case_id:
        sql += " WHERE case_id = ?"
        params.append(case_id)
    return [dict(r) for r in conn.execute(sql + " ORDER BY seq", params).fetchall()]


# =============================================================================
# Internal write helpers (no commit; called inside transactional services)
# =============================================================================

def _log(conn, actor: Actor, now: datetime, action: str, obj: str = "", case_id: str | None = None,
         before=None, after=None) -> None:
    db.append_audit(conn, ts=ts(now), user=actor.name, role=actor.role, action=action, obj=obj,
                    case_id=case_id, before=before, after=after)


def _bump_evidence_version(conn, case_id: str) -> int:
    conn.execute("UPDATE cases SET evidence_version = evidence_version + 1 WHERE case_id = ?", (case_id,))
    return conn.execute("SELECT evidence_version FROM cases WHERE case_id = ?", (case_id,)).fetchone()[0]


def _default_owner(conn, role: str, case: dict | None = None, exclude: tuple[str, ...] = ()) -> str:
    """Pick the named user who owns work for a role, avoiding anyone involved in the case."""
    involved = (set(case["involved_users"]) if case else set()) | set(exclude)
    if role == R.INVESTIGATOR and case and case.get("registered_by"):
        reg = get_actor(conn, case["registered_by"])
        if reg.role == R.INVESTIGATOR:
            return reg.user_id
    users = [u for u in list_users(conn) if u.role == role]
    if role == R.LEGAL_REVIEWER:
        users = [u for u in users if not u.is_external] + [u for u in users if u.is_external]
    for u in users:
        if u.user_id not in involved:
            return u.user_id
    return "system" if role == R.LEGAL_REVIEWER else (users[0].user_id if users else "system")


def _create_task(conn, actor: Actor, now: datetime, *, case_id: str, type: str, title: str,
                 owner: str, detail: str = "", schedule_due: date | None = None,
                 required: bool | None = None, urgent: bool = False, escalate_to: str | None = None,
                 linked_to: str | None = None, defect_id: str | None = None,
                 item_type: str | None = None) -> str:
    task_id = db.next_id(conn, "T")
    owner_role = get_actor(conn, owner).role if owner != "system" else "System"
    if required is None:
        required = type in REQUIRED_TASK_TYPES
    conn.execute(
        "INSERT INTO tasks (task_id, case_id, type, title, detail, owner, owner_role, created,"
        " schedule_due, status, required, urgent, escalate_to, linked_to, defect_id, item_type)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Open', ?, ?, ?, ?, ?, ?)",
        (task_id, case_id, type, title, detail, owner, owner_role, ts(now),
         schedule_due.isoformat() if schedule_due else None, int(required), int(urgent),
         escalate_to, linked_to, defect_id, item_type))
    _log(conn, actor, now, f"Task created: {type}", task_id, case_id,
         after={"title": title, "owner": user_name(conn, owner), "linked_to": linked_to})
    if urgent:
        target = escalate_to or R.TO_LEGAL_LEAD
        conn.execute("UPDATE tasks SET escalation_level = ? WHERE task_id = ?", (R.ESC_IMMEDIATE, task_id))
        _log(conn, SYSTEM_ACTOR, now, f"Immediate escalation to {target}", task_id, case_id,
             after={"reason": title})
    return task_id


def _close_task(conn, actor: Actor, now: datetime, task_id: str, outcome: str, note: str = "") -> None:
    before = conn.execute("SELECT status, outcome FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    conn.execute("UPDATE tasks SET status = 'Closed', closed_on = ?, closed_by = ?, outcome = ?,"
                 " closure_note = ? WHERE task_id = ?", (ts(now), actor.user_id, outcome, note, task_id))
    case_id = conn.execute("SELECT case_id FROM tasks WHERE task_id = ?", (task_id,)).fetchone()[0]
    _log(conn, actor, now, "Task closed", task_id, case_id, before=dict(before),
         after={"status": "Closed", "outcome": outcome, "note": note})


def _record_attempt(conn, actor: Actor, now: datetime, case_id: str, action: str, category: str,
                    outcome: str, reasons: list[str]) -> str:
    attempt_id = db.next_id(conn, "GA")
    conn.execute("INSERT INTO gate_attempts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 (attempt_id, case_id, ts(now), actor.user_id, actor.role, action, category, outcome,
                  db.to_json(reasons)))
    _log(conn, actor, now, f"{action}: {outcome.upper()}", attempt_id, case_id,
         after={"category": category, "reasons": reasons})
    return attempt_id


# =============================================================================
# Rule 2 / stage maintenance
# =============================================================================

def _relevant_defects(links: list[dict]) -> list[str]:
    return sorted(l["defect_id"] for l in links
                  if l["result"] == R.LINKED and not str(l.get("inquiry_status", "")).startswith("Closed – not"))


def _compute_evidence(conn, case: dict) -> list[R.EvidenceAssessment]:
    items = []
    for item in R.SUPPLIER_ITEMS:
        items.append(R.assess_supplier_item(item, case["disputed_start"], case["disputed_end"],
                                            case_deliveries(conn, case["case_id"], item)))
    links = case_links(conn, case["case_id"])
    n_defects = conn.execute("SELECT COUNT(*) FROM defects").fetchone()[0]
    items.append(R.assess_defect_search(links, n_defects))
    items.append(R.assess_spm_explanation(case["spm_explanation"]))
    statement = latest_statement(conn, case["case_id"])
    items.append(R.assess_expert_item(statement, latest_check(conn, statement), _relevant_defects(links)))
    return items


def _open_task(conn, case_id: str, type: str, item_type: str | None = None) -> dict | None:
    sql, params = "SELECT * FROM tasks WHERE case_id = ? AND type = ? AND status = 'Open'", [case_id, type]
    if item_type:
        sql += " AND item_type = ?"
        params.append(item_type)
    row = conn.execute(sql + " ORDER BY created DESC LIMIT 1", params).fetchone()
    return dict(row) if row else None


def _retrieval_title(assessment: R.EvidenceAssessment) -> str:
    if assessment.status == R.UNKNOWN:
        return f"Confirm whether {assessment.item_type.lower()} exist for the disputed period"
    if assessment.missing:
        spans = ", ".join(R.fmt_range(s, e) for s, e in assessment.missing)
        days = sum((e - s).days + 1 for s, e in assessment.missing)
        return f"Retrieve {assessment.item_type} for {spans} (missing {R.span_text(days)})"
    return f"Retrieve {assessment.item_type} for the disputed period"


def _sync_retrieval_tasks(conn, actor: Actor, now: datetime, case: dict,
                          assessments: list[R.EvidenceAssessment]) -> None:
    for a in assessments:
        if a.item_type not in R.SUPPLIER_ITEMS:
            continue
        task = _open_task(conn, case["case_id"], "Evidence retrieval", a.item_type)
        if a.status == R.COMPLETE:
            if task:
                _close_task(conn, SYSTEM_ACTOR, now, task["task_id"], "Delivered",
                            "Full disputed period now received")
            continue
        title = _retrieval_title(a)
        if task and task["title"] == title:
            continue
        if task:
            _close_task(conn, SYSTEM_ACTOR, now, task["task_id"], "Superseded",
                        "Partial or changed supplier response; replaced by a targeted request")
        exhausted = conn.execute(
            "SELECT 1 FROM tasks WHERE case_id = ? AND type = 'Evidence retrieval' AND item_type = ?"
            " AND title = ? AND outcome = ?", (case["case_id"], a.item_type, title, RETRIEVAL_UNAVAILABLE)
        ).fetchone()
        if exhausted:
            continue
        _create_task(conn, SYSTEM_ACTOR, now, case_id=case["case_id"], type="Evidence retrieval",
                     title=title, owner=_default_owner(conn, R.SUPPLIER_LIAISON, case),
                     detail=f"Rule 2: {a.item_type} is {a.status} — {a.reason}.",
                     schedule_due=R.add_working_days(now.date(), R.SUPPLIER_SCHEDULE_WD),
                     item_type=a.item_type)


def _authorised_exceptions(conn, case_id: str) -> dict[str, str]:
    rows = conn.execute("SELECT item_type, exception_id FROM exceptions WHERE case_id = ?"
                        " AND status = 'Authorised'", (case_id,)).fetchall()
    return {r["item_type"]: r["exception_id"] for r in rows}


def _gate_inputs(conn, case: dict) -> dict:
    open_required = []
    for t in case_tasks(conn, case["case_id"], open_only=True):
        if t["required"]:
            open_required.append({**t, "owner": user_name(conn, t["owner"])})
    review = latest_review(conn, case["case_id"], include_historical=False)
    if review:
        review = {**review, "reviewer": user_name(conn, review["reviewer"])}
    return dict(status=case["status"], evidence=evidence_items(conn, case["case_id"]),
                open_required=open_required, review=review,
                evidence_version=case["evidence_version"],
                authorised_exceptions=_authorised_exceptions(conn, case["case_id"]))


def case_gate(conn, case_id: str, include_review: bool = True) -> R.GateResult:
    case = get_case(conn, case_id)
    gate = R.evaluate_gate(**_gate_inputs(conn, case), include_review=include_review)
    for ex in case_exceptions(conn, case_id):
        if ex["status"] == "Proposed":
            gate.notes.append(f"Exception {ex['exception_id']} ({ex['item_type']}) proposed by "
                              f"{user_name(conn, ex['proposed_by'])}; awaiting separate authorisation by an "
                              "uninvolved legal lead or external legal reviewer.")
    return gate


def _sync_review_task(conn, now: datetime, case: dict) -> None:
    if case["status"] != "active":
        return
    pre = case_gate(conn, case["case_id"], include_review=False)
    review = latest_review(conn, case["case_id"], include_historical=False)
    current = review is not None and review["evidence_version"] == case["evidence_version"]
    task = _open_task(conn, case["case_id"], "Independent review")
    if not pre.blocked and not current and task is None:
        _create_task(conn, SYSTEM_ACTOR, now, case_id=case["case_id"], type="Independent review",
                     title="Record an independent, reasoned review decision",
                     owner=_default_owner(conn, R.LEGAL_REVIEWER, case), required=False,
                     detail="No blockers remain before review; a reviewer with no prior involvement must decide.")
    elif task is not None and (current or pre.blocked):
        note = (f"Review {review['review_id']} recorded" if current
                else "Returned to Stage 4: new evidence gaps or inquiries")
        _close_task(conn, SYSTEM_ACTOR, now, task["task_id"], "Closed", note)


def _compute_stage(conn, case: dict) -> int:
    open_tasks = case_tasks(conn, case["case_id"], open_only=True)
    if any(t["type"] == "Reassessment" for t in open_tasks):
        return 7
    if case["status"] == "closed":
        return 5
    pre = case_gate(conn, case["case_id"], include_review=False)
    return 4 if pre.blocked else 5


def _refresh(conn, actor: Actor, now: datetime, case_id: str) -> None:
    """Recompute Rule 2 coverage, follow-up tasks and the workflow stage for one case."""
    case = get_case(conn, case_id)
    assessments = _compute_evidence(conn, case)
    for a in assessments:
        old = conn.execute("SELECT * FROM evidence_items WHERE case_id = ? AND item_type = ?",
                           (case_id, a.item_type)).fetchone()
        flagged = a.status in (R.GAP, R.UNKNOWN)
        if old is None:
            since = now.date().isoformat() if flagged else None
        elif flagged and old["status"] in (R.GAP, R.UNKNOWN):
            since = old["since"]
        else:
            since = now.date().isoformat() if flagged else None
        owner = R.ITEM_OWNER_ROLE[a.item_type]
        conn.execute(
            "INSERT OR REPLACE INTO evidence_items (case_id, item_type, status, period_covered, reason,"
            " owner, since, updated_on) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (case_id, a.item_type, a.status, a.period_covered, a.reason, owner, since, ts(now)))
        if old is None or old["status"] != a.status or old["reason"] != a.reason:
            _log(conn, SYSTEM_ACTOR, now, f"Rule 2 coverage: {a.item_type}", a.item_type, case_id,
                 before=None if old is None else {"status": old["status"], "reason": old["reason"]},
                 after={"status": a.status, "reason": a.reason})
    if case["status"] == "active":
        _sync_retrieval_tasks(conn, actor, now, case, assessments)
        expert = next(a for a in assessments if a.item_type == R.EXPERT_STATEMENT)
        task = _open_task(conn, case_id, "Expert correction")
        if task and expert.status in (R.COMPLETE, R.NOT_APPLICABLE):
            _close_task(conn, SYSTEM_ACTOR, now, task["task_id"], "Corrected",
                        "Latest statement version checked with no omissions")
        _sync_review_task(conn, now, case)
    stage = _compute_stage(conn, case)
    if stage != case["stage"]:
        conn.execute("UPDATE cases SET stage = ? WHERE case_id = ?", (stage, case_id))
        _log(conn, SYSTEM_ACTOR, now, "Workflow stage changed", case_id, case_id,
             before={"stage": case["stage"]}, after={"stage": stage})


@transactional
@permitted("refresh_case")
def refresh_case(conn, actor: Actor, now: datetime, case_id: str) -> None:
    _refresh(conn, actor, now, case_id)


# =============================================================================
# Stage 1 – Register a case
# =============================================================================

@transactional
@permitted("register_case")
def register_case(conn, actor: Actor, now: datetime, data: dict,
                  source_file: str = "case_register_entry.json") -> Outcome:
    case_id = data["case_id"].strip()
    if conn.execute("SELECT 1 FROM cases WHERE case_id = ?", (case_id,)).fetchone():
        return Outcome(False, f"Case {case_id} already exists", [f"Case {case_id} already exists"])
    status = data.get("status", "active")
    involved = list(dict.fromkeys(data.get("involved_users", [])))
    if actor.role == R.INVESTIGATOR and status == "active" and actor.user_id not in involved:
        involved.insert(0, actor.user_id)
    notes = dict(data.get("involvement_notes", {}))
    if actor.user_id in involved and actor.user_id not in notes:
        notes[actor.user_id] = "Registering investigator"
    raw = {k: ("" if v is None else str(v)) for k, v in data.items() if k not in ("involvement_notes",)}
    record_id = db.add_source_record(conn, source_type="Case file (POL)", source_file=source_file,
                                     original_id=case_id, received_at=ts(now), payload=raw)

    def clean(v):
        return R.UNKNOWN if R.is_unknown(v) else str(v)

    conn.execute(
        "INSERT INTO cases (case_id, branch, branch_name, disputed_start, disputed_end, horizon_version,"
        " amount, stage, status, spm_explanation, involved_users, involvement_notes, legal_deadline,"
        " legal_deadline_note, registered_by, registered_on, closed_on, closure_note, source_record_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (case_id, clean(data.get("branch")), data.get("branch_name", ""),
         clean(data.get("disputed_start")), clean(data.get("disputed_end")),
         clean(data.get("horizon_version")), data.get("amount"), status,
         (data.get("spm_explanation") or "").strip() or None, db.to_json(involved), db.to_json(notes),
         data.get("legal_deadline"), data.get("legal_deadline_note"), actor.user_id, ts(now),
         data.get("closed_on"), data.get("closure_note"), record_id))
    _log(conn, actor, now, "Stage 1 Register: case registered", case_id, case_id,
         after={k: data.get(k) for k in ("branch", "disputed_start", "disputed_end",
                                         "horizon_version", "amount", "status")})
    if data.get("historical_decision"):
        hd = data["historical_decision"]
        review_id = db.next_id(conn, "RV")
        conn.execute(
            "INSERT INTO reviews (review_id, case_id, reviewer, conflict_declaration, evidence_version,"
            " decision, reasons, recorded_on, is_historical) VALUES (?, ?, ?, ?, 1, ?, ?, ?, 1)",
            (review_id, case_id, "system", "Not recorded (pre-CERT legacy file)", hd["decision"],
             hd["reasons"], hd["date"]))
        _log(conn, actor, now, "Original decision preserved from legacy file", review_id, case_id,
             after=hd)
    links = _screen_case(conn, actor, now, case_id)
    _refresh(conn, actor, now, case_id)
    flagged = [l for l in links if l.flagged]
    return Outcome(True, f"Case {case_id} registered; screened against {len(links)} defect records "
                         f"({len(flagged)} flagged for inquiry or manual review).",
                   data={"case_id": case_id})


# =============================================================================
# Stage 2 – Rule 1 linking and Rule 5 reassessment
# =============================================================================

def _store_link(conn, actor: Actor, now: datetime, case: dict, defect: dict, link: R.LinkResult,
                rule: str) -> None:
    old = conn.execute("SELECT * FROM defect_links WHERE case_id = ? AND defect_id = ?",
                       (case["case_id"], defect["defect_id"])).fetchone()
    inquiry = "Open" if link.flagged and case["status"] == "active" else (
        "Reassessment" if link.flagged else "n/a")
    if old is not None and old["result"] == link.result:
        conn.execute("UPDATE defect_links SET matched_fields = ?, explanation = ?, updated_on = ?,"
                     " defect_version = ? WHERE case_id = ? AND defect_id = ?",
                     (db.to_json(list(link.matched_fields)), link.explanation, ts(now),
                      defect["record_version"], case["case_id"], defect["defect_id"]))
        return
    conn.execute(
        "INSERT OR REPLACE INTO defect_links (case_id, defect_id, result, matched_fields, explanation,"
        " inquiry_status, inquiry_finding, created_by_rule, created_on, updated_on, defect_version)"
        " VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)",
        (case["case_id"], defect["defect_id"], link.result, db.to_json(list(link.matched_fields)),
         link.explanation, inquiry, rule, old["created_on"] if old else ts(now), ts(now),
         defect["record_version"]))
    _log(conn, actor if rule == "Rule 1" else SYSTEM_ACTOR, now, f"{rule}: {R.RESULT_LABELS[link.result]}",
         f"{case['case_id']} ↔ {defect['defect_id']}", case["case_id"],
         before=None if old is None else {"result": old["result"]},
         after={"result": link.result, "matched_fields": list(link.matched_fields),
                "explanation": link.explanation})
    if link.flagged or (old is not None and old["result"] != R.NO_MATCH):
        _bump_evidence_version(conn, case["case_id"])


def _screen_case(conn, actor: Actor, now: datetime, case_id: str) -> list[R.LinkResult]:
    """Rule 1 for a newly registered case against every defect on record."""
    case = get_case(conn, case_id)
    results = []
    for defect in list_defects(conn):
        link = R.match_defect(case, defect)
        _store_link(conn, SYSTEM_ACTOR, now, case, defect, link, "Rule 1")
        if link.flagged and case["status"] == "active":
            _create_inquiry_task(conn, now, case, defect, link)
        elif link.flagged and latest_review(conn, case_id):
            _create_reassessment_task(conn, now, case, defect, link)
        results.append(link)
    _log(conn, SYSTEM_ACTOR, now, "Stage 2 Link defects: Rule 1 screening complete", case_id, case_id,
         after={"defects_screened": len(results), "flagged": sum(l.flagged for l in results)})
    return results


def _create_inquiry_task(conn, now: datetime, case: dict, defect: dict, link: R.LinkResult,
                         title: str | None = None) -> str:
    manual = link.result == R.MANUAL_REVIEW
    default = (f"Manual review: decide whether {defect['defect_id']} is relevant ("
               f"{', '.join(link.unknown_fields)} Unknown)" if manual
               else f"Inquire into {defect['defect_id']}: compare symptoms with branch transactions")
    return _create_task(conn, SYSTEM_ACTOR, now, case_id=case["case_id"],
                        type="Manual review" if manual else "Defect inquiry",
                        title=title or default, owner=_default_owner(conn, R.INVESTIGATOR, case),
                        detail=link.explanation, defect_id=defect["defect_id"],
                        item_type=R.DEFECT_SEARCH if manual else None)


def _create_reassessment_task(conn, now: datetime, case: dict, defect: dict, link: R.LinkResult) -> str:
    """Rule 5: a reassessment task that preserves the original decision and its reasoning."""
    original = latest_review(conn, case["case_id"])
    preserved = (f"Original decision {original['review_id']} ({R.fmt_date(original['recorded_on'])}): "
                 f"“{original['decision']}”. Reasons: {original['reasons']}")
    owner = _default_owner(conn, R.LEGAL_REVIEWER, case, exclude=(original["reviewer"],))
    task_id = _create_task(
        conn, SYSTEM_ACTOR, now, case_id=case["case_id"], type="Reassessment",
        title=f"Reassess earlier decision {original['review_id']} in light of {defect['defect_id']}",
        owner=owner,
        detail=f"{link.explanation}\n\n{preserved}",
        linked_to=original["review_id"], defect_id=defect["defect_id"])
    if owner == "system":
        _create_task(conn, SYSTEM_ACTOR, now, case_id=case["case_id"], type="Escalation",
                     title="Assign an independent reviewer: no eligible reviewer available", owner=_default_owner(conn, R.COMMITTEE),
                     urgent=True, escalate_to=R.TO_COMMITTEE, linked_to=task_id)
    return task_id


@transactional
@permitted("load_defect")
def load_defect(conn, actor: Actor, now: datetime, record: dict,
                source_file: str = "defect_entry_form") -> Outcome:
    """Add or update a PEAK/KEL record, then run Rule 5 across every case."""
    raw = {k: ("" if record.get(k) is None else str(record.get(k))) for k in DEFECT_CSV_FIELDS}
    defect_id = raw["defect_id"].strip()
    if not defect_id:
        return Outcome(False, "A defect ID is required", ["A defect ID is required"])
    record_id = db.add_source_record(conn, source_type="PEAK/KEL (Fujitsu)", source_file=source_file,
                                     original_id=defect_id, received_at=ts(now), payload=raw)
    branches = R.as_scope(raw["affected_branches"])
    versions = R.as_scope(raw["versions"])
    values = {
        "type": raw["type"].strip() or ("KEL" if defect_id.upper().startswith("KEL") else "PEAK"),
        "affected_branches": db.to_json(R.UNKNOWN if branches is None else
                                        (R.ALL_BRANCHES if branches == R.ALL_BRANCHES else list(branches))),
        "affected_start": raw["affected_start"].strip() or R.UNKNOWN,
        "affected_end": raw["affected_end"].strip() or R.UNKNOWN,
        "versions": db.to_json(R.UNKNOWN if versions is None else
                               (R.ALL_BRANCHES if versions == R.ALL_BRANCHES else list(versions))),
        "symptoms": raw["symptoms"].strip(),
        "date_reported": raw["date_reported"].strip() or R.UNKNOWN,
    }
    existing = get_defect(conn, defect_id)
    if existing:
        conn.execute(
            "UPDATE defects SET type = :type, affected_branches = :affected_branches,"
            " affected_start = :affected_start, affected_end = :affected_end, versions = :versions,"
            " symptoms = :symptoms, date_reported = :date_reported, loaded_on = :loaded_on,"
            " record_version = record_version + 1, source_record_id = :sr WHERE defect_id = :id",
            {**values, "loaded_on": ts(now), "sr": record_id, "id": defect_id})
        action = "Defect record updated"
    else:
        conn.execute(
            "INSERT INTO defects (defect_id, type, affected_branches, affected_start, affected_end,"
            " versions, symptoms, date_reported, loaded_on, record_version, source_record_id)"
            " VALUES (:id, :type, :affected_branches, :affected_start, :affected_end, :versions,"
            " :symptoms, :date_reported, :loaded_on, 1, :sr)",
            {**values, "loaded_on": ts(now), "sr": record_id, "id": defect_id})
        action = "Defect record loaded"
    defect = get_defect(conn, defect_id)
    _log(conn, actor, now, action, defect_id, None,
         before=None if existing is None else {k: existing[k] for k in ("affected_branches", "affected_start",
                                                                       "affected_end", "versions")},
         after={**raw, "source_record": record_id})
    summary = _reassess_all(conn, actor, now, defect)
    summary["action"] = action
    msg = (f"Rule 5 re-screened {summary['cases_screened']} cases (open and closed, regardless of date): "
           f"{summary['linked']} potential link(s), {summary['manual']} manual-review item(s), "
           f"{summary['reassessment_tasks']} reassessment task(s) created.")
    return Outcome(True, msg, data=summary)


def _reassess_all(conn, actor: Actor, now: datetime, defect: dict) -> dict:
    cases = list_cases(conn)
    for c in cases:
        decision = latest_review(conn, c["case_id"])
        c["latest_decision_id"] = decision["review_id"] if decision else None
    previous = {r["case_id"]: r["result"] for r in conn.execute(
        "SELECT case_id, result FROM defect_links WHERE defect_id = ?", (defect["defect_id"],))}
    actions = R.plan_reassessment(defect, cases, previous)
    summary = {"defect_id": defect["defect_id"], "cases_screened": len(actions), "linked": 0, "manual": 0,
               "reassessment_tasks": 0, "inquiry_tasks": 0, "rows": []}
    by_id = {c["case_id"]: c for c in cases}
    for a in actions:
        case = by_id[a.case_id]
        _store_link(conn, actor, now, case, defect, a.link, "Rule 5")
        tasks_created = []
        if a.create_inquiry:
            title = (f"Defect record {defect['defect_id']} amended: confirm whether the earlier link "
                     "still applies") if a.withdrawn else None
            link = a.link if not a.withdrawn else R.LinkResult(R.MANUAL_REVIEW, a.link.matched_fields,
                                                               a.link.unknown_fields, a.link.failed_fields,
                                                               a.link.explanation)
            tasks_created.append(_create_inquiry_task(conn, now, case, defect, link, title))
            summary["inquiry_tasks"] += 1
        if a.create_reassessment:
            tasks_created.append(_create_reassessment_task(conn, now, case, defect, a.link))
            summary["reassessment_tasks"] += 1
        if a.link.result == R.LINKED:
            summary["linked"] += 1
        elif a.link.result == R.MANUAL_REVIEW:
            summary["manual"] += 1
        summary["rows"].append({
            "case_id": a.case_id, "status": case["status"], "result": R.RESULT_LABELS[a.link.result],
            "previous": R.RESULT_LABELS.get(a.previous_result, "—"),
            "tasks_created": ", ".join(tasks_created) or "—", "explanation": a.link.explanation})
        _refresh(conn, actor, now, a.case_id)
    _log(conn, SYSTEM_ACTOR, now, "Rule 5 reassessment run", defect["defect_id"], None,
         after={k: v for k, v in summary.items() if k != "rows"})
    return summary


def parse_defect_csv(text: str) -> tuple[list[dict], list[str]]:
    reader = csv.DictReader(io.StringIO(text))
    missing = [f for f in ("defect_id", "affected_branches", "affected_start", "affected_end", "versions")
               if f not in (reader.fieldnames or [])]
    if missing:
        return [], [f"CSV is missing required column(s): {', '.join(missing)}"]
    rows = [{k: (row.get(k) or "").strip() for k in DEFECT_CSV_FIELDS} for row in reader]
    return [r for r in rows if r["defect_id"]], []


# =============================================================================
# Stage 3 – Supplier evidence (Rule 2) and helpline records
# =============================================================================

@transactional
@permitted("load_complaints")
def load_complaints(conn, actor: Actor, now: datetime, rows: list[dict], source_file: str) -> Outcome:
    if actor.role == R.INVESTIGATOR:
        branches = {c["branch"] for c in visible_cases(conn, actor)}
        if any(str(row.get("branch", "")) not in branches for row in rows):
            _log(conn, actor, now, "Permission denied: complaint scope", source_file)
            return Outcome(False, "Complaint import refused", ["An investigator can import complaints only for their case branches"])
    for row in rows:
        raw = {k: str(row.get(k, "")) for k in ("complaint_id", "branch", "date", "issue")}
        record_id = db.add_source_record(conn, source_type="Helpline / complaint (POL)", source_file=source_file,
                                         original_id=raw["complaint_id"], received_at=ts(now), payload=raw)
        conn.execute("INSERT OR REPLACE INTO complaints VALUES (?, ?, ?, ?, ?)",
                     (raw["complaint_id"], raw["branch"], raw["date"] or R.UNKNOWN, raw["issue"], record_id))
    _log(conn, actor, now, "Helpline records loaded", source_file, None, after={"records": len(rows)})
    return Outcome(True, f"{len(rows)} helpline records loaded")


@transactional
@permitted("record_supplier_delivery")
def record_supplier_delivery(conn, actor: Actor, now: datetime, *, case_id: str, item_type: str,
                             request_ref: str, period_start, period_end, availability: str,
                             notes: str = "", source_file: str | None = None) -> Outcome:
    payload = {"case_id": case_id, "item_type": item_type, "request_ref": request_ref,
               "period_start": str(period_start or ""), "period_end": str(period_end or ""),
               "availability": availability, "notes": notes}
    record_id = db.add_source_record(conn, source_type=f"{item_type} (Fujitsu)",
                                     source_file=source_file or f"{request_ref}_receipt.json",
                                     original_id=request_ref, received_at=ts(now), payload=payload)
    delivery_id = db.next_id(conn, "DL")
    conn.execute("INSERT INTO supplier_deliveries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 (delivery_id, case_id, item_type, request_ref,
                  str(period_start) if period_start else None, str(period_end) if period_end else None,
                  availability, ts(now), notes, actor.user_id, record_id))
    _log(conn, actor, now, f"Supplier delivery recorded: {item_type}", delivery_id, case_id, after=payload)
    _bump_evidence_version(conn, case_id)
    _refresh(conn, actor, now, case_id)
    item = next(i for i in evidence_items(conn, case_id) if i["item_type"] == item_type)
    return Outcome(True, f"{item_type}: now {item['status']} — {item['reason']}")


@transactional
@permitted("close_retrieval_unavailable")
def close_retrieval_unavailable(conn, actor: Actor, now: datetime, task_id: str,
                                steps_taken: str) -> Outcome:
    task = dict(conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone())
    problems = []
    if task["type"] != "Evidence retrieval" or task["status"] != "Open":
        problems.append("Only an open evidence-retrieval request can be closed as unavailable")
    if actor.role not in (R.SUPPLIER_LIAISON, R.LEGAL_LEAD):
        problems.append("Only the supplier liaison manager or legal lead may record retrieval as exhausted")
    if len((steps_taken or "").strip()) < 20:
        problems.append("Document the retrieval steps taken (who was asked, when, and the response)")
    if problems:
        return Outcome(False, "Not recorded", problems)
    _close_task(conn, actor, now, task_id, RETRIEVAL_UNAVAILABLE, steps_taken.strip())
    _bump_evidence_version(conn, task["case_id"])
    _refresh(conn, actor, now, task["case_id"])
    return Outcome(True, "Retrieval recorded as exhausted. The gap stays visible; any reliance now needs an "
                         "independently authorised exception.")


# =============================================================================
# Stage 4 – Investigate: inquiries, expert completeness
# =============================================================================

@transactional
@permitted("record_inquiry_outcome")
def record_inquiry_outcome(conn, actor: Actor, now: datetime, task_id: str, *, outcome: str,
                           finding: str, may_undermine: bool = False) -> Outcome:
    task = dict(conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone())
    problems = []
    if task["type"] not in ("Defect inquiry", "Manual review") or task["status"] != "Open":
        problems.append("Only an open defect inquiry or manual-review task can be completed here")
    if actor.role not in (R.INVESTIGATOR, R.TECH_REVIEWER):
        problems.append("Inquiries are completed by the investigator or technical reviewer")
    if len((finding or "").strip()) < 15:
        problems.append("Record the finding and the evidence compared (symptoms vs transactions)")
    if problems:
        return Outcome(False, "Not recorded", problems)
    case = get_case(conn, task["case_id"])
    status = "Closed – relevant" if outcome == INQUIRY_RELEVANT else "Closed – not relevant"
    if task["type"] == "Manual review" and outcome == INQUIRY_RELEVANT:
        conn.execute("UPDATE defect_links SET result = ? WHERE case_id = ? AND defect_id = ?",
                     (R.LINKED, case["case_id"], task["defect_id"]))
    conn.execute("UPDATE defect_links SET inquiry_status = ?, inquiry_finding = ?, updated_on = ?"
                 " WHERE case_id = ? AND defect_id = ?",
                 (status, finding.strip(), ts(now), case["case_id"], task["defect_id"]))
    _close_task(conn, actor, now, task_id, outcome, finding.strip())
    _bump_evidence_version(conn, case["case_id"])
    if may_undermine and case["status"] == "active":
        _create_task(conn, actor, now, case_id=case["case_id"], type="Escalation",
                     title=f"Material that may undermine the case: {task['defect_id']}",
                     owner=_default_owner(conn, R.LEGAL_LEAD, case), urgent=True,
                     escalate_to=R.TO_LEGAL_LEAD, defect_id=task["defect_id"],
                     detail=f"Investigator finding: {finding.strip()}")
    _refresh(conn, actor, now, case["case_id"])
    return Outcome(True, f"Inquiry {task_id} closed: {outcome}"
                         + ("; immediate escalation to the legal lead" if may_undermine else ""))


@transactional
@permitted("record_expert_statement")
def record_expert_statement(conn, actor: Actor, now: datetime, *, case_id: str, statement_id: str,
                            author: str, defects_addressed: list[str], summary: str = "") -> Outcome:
    prev = latest_statement(conn, case_id)
    version = (prev["version"] + 1) if prev and prev["statement_id"] == statement_id else 1
    payload = {"statement_id": statement_id, "version": version, "author": author,
               "defects_addressed": sorted(defects_addressed), "summary": summary}
    record_id = db.add_source_record(conn, source_type="Expert statement", source_file=f"{statement_id}_v{version}.pdf",
                                     original_id=f"{statement_id} v{version}", received_at=ts(now),
                                     payload=payload)
    conn.execute("INSERT INTO expert_statements VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 (statement_id, case_id, author, version, db.to_json(sorted(defects_addressed)), summary,
                  ts(now), record_id))
    _log(conn, actor, now, "Expert statement recorded", f"{statement_id} v{version}", case_id, after=payload)
    _bump_evidence_version(conn, case_id)
    _refresh(conn, actor, now, case_id)
    return Outcome(True, f"{statement_id} v{version} recorded; a completeness check is now required.")


@transactional
@permitted("run_expert_check")
def run_expert_check(conn, actor: Actor, now: datetime, case_id: str, notes: str = "") -> Outcome:
    if actor.role != R.TECH_REVIEWER:
        return Outcome(False, "Not run", ["The expert completeness check is performed by a technical reviewer"])
    statement = latest_statement(conn, case_id)
    if statement is None:
        return Outcome(False, "Not run", ["No expert statement is recorded for this case"])
    relevant = _relevant_defects(case_links(conn, case_id))
    omissions = R.expert_completeness(statement["linked_defects"], relevant)
    check_id = db.next_id(conn, "XC")
    status = "Correction requested" if omissions else "No omissions"
    conn.execute("INSERT INTO expert_checks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 (check_id, statement["statement_id"], statement["version"], case_id, actor.user_id, ts(now),
                  db.to_json(relevant), db.to_json(omissions), status, notes))
    _log(conn, actor, now, "Expert completeness check", check_id, case_id,
         after={"statement": f"{statement['statement_id']} v{statement['version']}",
                "relevant_defects": relevant, "omissions": omissions, "status": status})
    _bump_evidence_version(conn, case_id)
    if omissions and not _open_task(conn, case_id, "Expert correction"):
        case = get_case(conn, case_id)
        _create_task(conn, actor, now, case_id=case_id, type="Expert correction",
                     title=f"Obtain corrected statement addressing {', '.join(omissions)}",
                     owner=_default_owner(conn, R.TECH_REVIEWER, case), item_type=R.EXPERT_STATEMENT,
                     detail=f"{statement['statement_id']} v{statement['version']} ({statement['author']}) omits "
                            f"{', '.join(omissions)}. Independent legal reviewer to assess implications.")
    _refresh(conn, actor, now, case_id)
    if omissions:
        return Outcome(True, f"Omission recorded: {', '.join(omissions)}. Correction requested; gate stays blocked.",
                       data={"omissions": omissions})
    return Outcome(True, "No omissions against linked defects.", data={"omissions": []})


# =============================================================================
# Stage 5 – Independent review and the reliance gate (Rule 3)
# =============================================================================

@transactional
def record_review(conn, actor: Actor, now: datetime, case_id: str, *, declared_no_involvement: bool,
                  decision: str, reasons: str, conflict_note: str = "") -> Outcome:
    case = get_case(conn, case_id)
    problems, self_review = R.review_problems(
        reviewer_id=actor.user_id, reviewer_name=actor.name, reviewer_role=actor.role,
        involved_users=case["involved_users"], declared_no_involvement=declared_no_involvement,
        reasons=reasons)
    if case["status"] != "active":
        problems.append("Closed cases are reviewed through their reassessment task")
    if decision == R.RELY and not problems:
        pre = case_gate(conn, case_id, include_review=False)
        if pre.blocked:
            problems.append(f"“Reliance may proceed” cannot be recorded while {len(pre.reasons)} "
                            f"blocker{'s' if len(pre.reasons) != 1 else ''} remain{'s' if len(pre.reasons) == 1 else ''}:")
            problems += [f"• {r}" for r in pre.reasons]
    if problems:
        category = "self_review" if self_review else "review"
        _record_attempt(conn, actor, now, case_id, f"Review “{decision}”", category, "Blocked", problems)
        return Outcome(False, "Review blocked and logged", problems, {"self_review": self_review})
    exception = _authorised_exceptions(conn, case_id)
    exc_ids = ", ".join(exception.values()) or None
    authoriser = None
    if exc_ids:
        row = conn.execute("SELECT authoriser FROM exceptions WHERE exception_id = ?",
                           (next(iter(exception.values())),)).fetchone()
        authoriser = row["authoriser"]
    review_id = db.next_id(conn, "RV")
    declaration = "No prior involvement declared" + (f" ({conflict_note.strip()})" if conflict_note.strip() else "")
    conn.execute(
        "INSERT INTO reviews (review_id, case_id, reviewer, conflict_declaration, evidence_version, decision,"
        " reasons, exception_flag, exception_authoriser, exception_id, recorded_on, is_historical)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
        (review_id, case_id, actor.user_id, declaration, case["evidence_version"], decision, reasons.strip(),
         int(bool(exc_ids)), authoriser, exc_ids, ts(now)))
    _log(conn, actor, now, "Stage 5 Independent review recorded", review_id, case_id,
         after={"decision": decision, "evidence_version": case["evidence_version"],
                "conflict_declaration": declaration, "exception": exc_ids})
    _refresh(conn, actor, now, case_id)
    return Outcome(True, f"Review {review_id} recorded: {decision}", data={"review_id": review_id})


@transactional
@permitted("attempt_reliance")
def attempt_reliance(conn, actor: Actor, now: datetime, case_id: str, action: str) -> Outcome:
    if action not in R.RELIANCE_ACTIONS:
        _record_attempt(conn, actor, now, case_id, action, "reliance", "Blocked", ["Unknown reliance action"])
        return Outcome(False, "Unknown reliance action", ["Select an authorised reliance action"])
    gate = case_gate(conn, case_id)
    if gate.state == R.CLEAR:
        _record_attempt(conn, actor, now, case_id, action, "reliance", "Permitted", gate.notes)
        return Outcome(True, f"{action}: permitted by the reliance gate", data={"gate": gate})
    reasons = gate.reasons or ["Case is closed; no reliance action is open"]
    _record_attempt(conn, actor, now, case_id, action, "reliance", "Blocked", reasons)
    return Outcome(False, f"{action}: BLOCKED by the reliance gate", reasons, {"gate": gate})


def _retrieval_exhausted(conn, case_id: str, item_type: str) -> bool:
    return conn.execute("SELECT 1 FROM tasks WHERE case_id = ? AND type = 'Evidence retrieval' AND item_type = ?"
                        " AND outcome = ?", (case_id, item_type, RETRIEVAL_UNAVAILABLE)).fetchone() is not None


def _escalate_rejection(conn, actor: Actor, now: datetime, case: dict, what: str, problems: list[str]) -> str:
    legal_lead = _default_owner(conn, R.LEGAL_LEAD)
    conflicted = actor.role == R.LEGAL_LEAD or legal_lead in case["involved_users"]
    target = R.TO_COMMITTEE if conflicted else R.TO_LEGAL_LEAD
    owner = _default_owner(conn, R.COMMITTEE) if conflicted else legal_lead
    return _create_task(conn, actor, now, case_id=case["case_id"], type="Escalation",
                        title=f"Rejected {what} by {actor.name}", owner=owner, urgent=True,
                        escalate_to=target, detail="; ".join(problems))


@transactional
def propose_exception(conn, actor: Actor, now: datetime, case_id: str, *, item_type: str,
                      implications: str, proposed_action: str, reasons: str,
                      duties_confirmed: bool) -> Outcome:
    case = get_case(conn, case_id)
    item = next(i for i in evidence_items(conn, case_id) if i["item_type"] == item_type)
    open_required = _gate_inputs(conn, case)["open_required"]
    problems = R.exception_proposal_problems(
        proposer_id=actor.user_id, proposer_name=actor.name, proposer_role=actor.role,
        involved_users=case["involved_users"], item_type=item_type, item_status=item["status"],
        retrieval_exhausted=_retrieval_exhausted(conn, case_id, item_type), open_required=open_required,
        implications=implications, proposed_action=proposed_action, reasons=reasons,
        duties_confirmed=duties_confirmed)
    if problems:
        _record_attempt(conn, actor, now, case_id, "Propose unavailable-evidence exception",
                        "exception_proposal", "Blocked", problems)
        task_id = _escalate_rejection(conn, actor, now, case, "exception proposal", problems)
        return Outcome(False, f"Exception rejected, logged and escalated ({task_id})", problems)
    exception_id = db.next_id(conn, "EX")
    gap = f"{item_type}: {item['status']} — {item['reason']}"
    conn.execute("INSERT INTO exceptions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Proposed', NULL, NULL)",
                 (exception_id, case_id, item_type, gap, implications.strip(), proposed_action.strip(),
                  reasons.strip(), int(duties_confirmed), actor.user_id, ts(now)))
    _log(conn, actor, now, "Unavailable-evidence exception proposed", exception_id, case_id,
         after={"gap": gap, "implications": implications, "proposed_action": proposed_action})
    return Outcome(True, f"Exception {exception_id} proposed; it needs separate authorisation by an "
                         "uninvolved legal lead or external legal reviewer.", data={"exception_id": exception_id})


@transactional
def authorise_exception(conn, actor: Actor, now: datetime, exception_id: str,
                        independence_confirmed: bool) -> Outcome:
    ex = dict(conn.execute("SELECT * FROM exceptions WHERE exception_id = ?", (exception_id,)).fetchone())
    case = get_case(conn, ex["case_id"])
    problems = R.exception_authorisation_problems(
        authoriser_id=actor.user_id, authoriser_name=actor.name, authoriser_role=actor.role,
        authoriser_external=actor.is_external, proposer_id=ex["proposed_by"],
        involved_users=case["involved_users"], open_required=_gate_inputs(conn, case)["open_required"],
        independence_confirmed=independence_confirmed)
    if ex["status"] != "Proposed":
        problems.append(f"Exception {exception_id} is {ex['status']}, not awaiting authorisation")
    if problems:
        _record_attempt(conn, actor, now, ex["case_id"], f"Authorise exception {exception_id}",
                        "exception_authorisation", "Blocked", problems)
        task_id = _escalate_rejection(conn, actor, now, case, f"authorisation of {exception_id}", problems)
        return Outcome(False, f"Authorisation rejected, logged and escalated ({task_id})", problems)
    conn.execute("UPDATE exceptions SET status = 'Authorised', authoriser = ?, authorised_on = ?"
                 " WHERE exception_id = ?", (actor.user_id, ts(now), exception_id))
    _log(conn, actor, now, "Unavailable-evidence exception authorised", exception_id, ex["case_id"],
         before={"status": "Proposed"}, after={"status": "Authorised", "authoriser": actor.name})
    _bump_evidence_version(conn, ex["case_id"])
    _refresh(conn, actor, now, ex["case_id"])
    return Outcome(True, f"Exception {exception_id} authorised. The gap remains visible on the case.")


# =============================================================================
# Stage 6/7 – Escalation handling and reassessment
# =============================================================================

@transactional
@permitted("acknowledge_escalation")
def acknowledge_escalation(conn, actor: Actor, now: datetime, task_id: str, note: str) -> Outcome:
    task = dict(conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone())
    if task["type"] != "Escalation" or task["status"] != "Open":
        return Outcome(False, "Not recorded", ["Only an open escalation can be acknowledged here"])
    if actor.role not in (R.LEGAL_LEAD, R.COMMITTEE):
        return Outcome(False, "Not recorded", ["Escalations are resolved by the legal lead or the Committee"])
    if task["escalate_to"] == R.TO_COMMITTEE and actor.role != R.COMMITTEE:
        return Outcome(False, "Not recorded", ["This escalation requires Committee action"])
    if actor.user_id in get_case(conn, task["case_id"])["involved_users"]:
        return Outcome(False, "Not recorded", [f"{actor.name} is involved in this case; route to the Committee"])
    if len((note or "").strip()) < 10:
        return Outcome(False, "Not recorded", ["Record the action taken"])
    _close_task(conn, actor, now, task_id, "Acknowledged", note.strip())
    _refresh(conn, actor, now, task["case_id"])
    return Outcome(True, f"Escalation {task_id} acknowledged")


@transactional
def complete_reassessment(conn, actor: Actor, now: datetime, task_id: str, *, outcome: str,
                          reasons: str, declared_no_involvement: bool) -> Outcome:
    task = dict(conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone())
    case = get_case(conn, task["case_id"])
    problems, self_review = R.review_problems(
        reviewer_id=actor.user_id, reviewer_name=actor.name, reviewer_role=actor.role,
        involved_users=case["involved_users"], declared_no_involvement=declared_no_involvement, reasons=reasons)
    if task["type"] != "Reassessment" or task["status"] != "Open":
        problems.append("Only an open reassessment task can be completed here")
    original = conn.execute("SELECT * FROM reviews WHERE review_id = ?", (task["linked_to"],)).fetchone()
    if actor.user_id != task["owner"]:
        problems.append("Only the assigned independent reviewer can complete this reassessment")
    if original and original["reviewer"] == actor.user_id:
        problems.append("The original reviewer cannot reassess their own decision")
    if outcome not in (REASSESS_REFER, REASSESS_NO_REFERRAL):
        problems.append("Select a recognised reassessment outcome")
    if outcome == REASSESS_NO_REFERRAL:
        unresolved = [t for t in case_tasks(conn, case["case_id"], open_only=True)
                      if t["required"] and t["task_id"] != task_id]
        if unresolved:
            problems.append("No-referral closure requires completion of all other required inquiries: "
                            + ", ".join(t["task_id"] for t in unresolved))
        if any(i["status"] in (R.GAP, R.UNKNOWN) and i["item_type"] not in _authorised_exceptions(conn, case["case_id"])
               for i in evidence_items(conn, case["case_id"])):
            problems.append("Resolve or validly except evidence gaps before concluding no referral is needed")
    if problems:
        _record_attempt(conn, actor, now, case["case_id"], f"Complete reassessment {task_id}",
                        "self_review" if self_review else "review", "Blocked", problems)
        return Outcome(False, "Reassessment blocked and logged", problems)
    _close_task(conn, actor, now, task_id, outcome, reasons.strip())
    if outcome == REASSESS_REFER:
        owner = _default_owner(conn, R.LEGAL_LEAD, case)
        if owner in case["involved_users"]:
            owner = _default_owner(conn, R.COMMITTEE, case)
        _create_task(conn, actor, now, case_id=case["case_id"], type="Referral follow-up",
                     title=f"Track referral of earlier decision {task['linked_to']}",
                     owner=owner, required=True,
                     linked_to=task["linked_to"], defect_id=task["defect_id"],
                     detail="Referral recorded, not confirmed received or resolved. " + reasons.strip())
    _refresh(conn, actor, now, case["case_id"])
    return Outcome(True, f"Reassessment {task_id} recorded: {outcome}. The original decision "
                         f"{task['linked_to']} is preserved unchanged.")


@transactional
@permitted("assign_reassessment")
def assign_reassessment(conn, actor: Actor, now: datetime, task_id: str, reviewer_id: str) -> Outcome:
    task = dict(conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone())
    case = get_case(conn, task["case_id"])
    reviewer = get_actor(conn, reviewer_id)
    original = conn.execute("SELECT reviewer FROM reviews WHERE review_id = ?", (task["linked_to"],)).fetchone()
    if task["type"] != "Reassessment" or task["status"] != "Open":
        return Outcome(False, "Assignment refused", ["Only an open reassessment can be assigned"])
    if actor.user_id in case["involved_users"]:
        return Outcome(False, "Assignment refused", ["An involved manager cannot assign the reviewer"])
    if reviewer.role != R.LEGAL_REVIEWER or reviewer_id in case["involved_users"] or (original and reviewer_id == original[0]):
        return Outcome(False, "Assignment refused", ["Choose an uninvolved legal reviewer other than the original reviewer"])
    conn.execute("UPDATE tasks SET owner = ?, owner_role = ? WHERE task_id = ?", (reviewer_id, reviewer.role, task_id))
    _log(conn, actor, now, "Reassessment assigned", task_id, case["case_id"],
         before={"owner": task["owner"]}, after={"owner": reviewer_id})
    return Outcome(True, "Independent reassessment reviewer assigned")


@transactional
@permitted("record_referral_followup")
def record_referral_followup(conn, actor: Actor, now: datetime, task_id: str, evidence: str) -> Outcome:
    task = dict(conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone())
    case = get_case(conn, task["case_id"])
    if task["type"] != "Referral follow-up" or task["status"] != "Open":
        return Outcome(False, "Not recorded", ["Only an open referral follow-up can be completed"])
    if actor.user_id != task["owner"] or actor.user_id in case["involved_users"]:
        return Outcome(False, "Not recorded", ["Only the assigned uninvolved owner may record referral follow-through"])
    if len(evidence.strip()) < 20:
        return Outcome(False, "Not recorded", ["Record recipient, receipt reference and the documented response or next step"])
    _close_task(conn, actor, now, task_id, "Receipt and response documented", evidence.strip())
    _refresh(conn, actor, now, task["case_id"])
    return Outcome(True, "Referral follow-through recorded. Other required work and gate checks still apply.")


@transactional
@permitted("close_case")
def close_case(conn, actor: Actor, now: datetime, case_id: str, note: str) -> Outcome:
    case = get_case(conn, case_id)
    conn.execute("UPDATE cases SET status = 'closed', closed_on = ?, closure_note = ? WHERE case_id = ?",
                 (now.date().isoformat(), note, case_id))
    for t in case_tasks(conn, case_id, open_only=True):
        if t["type"] == "Independent review":
            _close_task(conn, SYSTEM_ACTOR, now, t["task_id"], "Closed", "Case closed")
    _log(conn, actor, now, "Case closed", case_id, case_id, before={"status": case["status"]},
         after={"status": "closed", "note": note})
    _refresh(conn, actor, now, case_id)
    return Outcome(True, f"Case {case_id} closed")


def _case_deadline(case: dict) -> date | None:
    d = R.parse_date(case.get("legal_deadline"))
    return d if isinstance(d, date) else None


def task_escalation(task: dict, case: dict, today: date) -> R.Escalation:
    created = datetime.strptime(task["created"], "%Y-%m-%d %H:%M").date()
    deadline = _case_deadline(case) if case["status"] == "active" else None
    return R.assess_escalation(created, today, urgent=bool(task["urgent"]), legal_deadline=deadline,
                               immediate_target=task["escalate_to"] or R.TO_LEGAL_LEAD)


@transactional
def run_escalation_sweep(conn, now: datetime) -> int:
    """Rule 4. Raise and log escalations reached by the demo clock (never lowers stored levels)."""
    cases = {c["case_id"]: c for c in list_cases(conn)}
    raised = 0
    for t in case_tasks(conn, open_only=True):
        esc = task_escalation(t, cases[t["case_id"]], now.date())
        if R.ESC_SEVERITY[esc.level] > R.ESC_SEVERITY.get(t["escalation_level"], 0):
            conn.execute("UPDATE tasks SET escalation_level = ? WHERE task_id = ?", (esc.level, t["task_id"]))
            _log(conn, SYSTEM_ACTOR, now, f"Rule 4 escalation: {esc.label}", t["task_id"], t["case_id"],
                 before={"level": t["escalation_level"]}, after={"level": esc.level, "reason": esc.reason})
            raised += 1
    return raised


# =============================================================================
# Integrity, export and oversight reporting
# =============================================================================

@transactional
@permitted("simulate_tampering")
def simulate_tampering(conn, actor: Actor, now: datetime, record_id: str, field_name: str, new_value: str) -> Outcome:
    """Demo only: an administrator bypasses the app and edits a stored source record."""
    row = conn.execute("SELECT raw_content FROM source_records WHERE record_id = ?", (record_id,)).fetchone()
    payload = db.from_json(row["raw_content"], {})
    old_value = payload.get(field_name)
    payload[field_name] = new_value
    conn.execute("DROP TRIGGER IF EXISTS source_records_no_update")
    conn.execute("UPDATE source_records SET raw_content = ? WHERE record_id = ?",
                 (db.canonical_json(payload), record_id))
    conn.execute("CREATE TRIGGER IF NOT EXISTS source_records_no_update BEFORE UPDATE ON source_records "
                 "BEGIN SELECT RAISE(ABORT, 'source_records are immutable; add a new version instead'); END;")
    _log(conn, actor, now, "DEMO: simulated out-of-band edit (protections bypassed)", record_id, None,
         before={field_name: old_value}, after={field_name: new_value})
    return Outcome(True, f"{record_id}.{field_name} changed from {old_value!r} to {new_value!r} outside CERT.")


def evidence_index(conn, case_id: str) -> list[dict]:
    """Exported evidence index: assists, but does not replace, the reviewer's disclosure schedule."""
    case = get_case(conn, case_id)
    rows = []
    for i in evidence_items(conn, case_id):
        rows.append({"section": "Evidence coverage", "item": i["item_type"], "status": i["status"],
                     "detail": f"{i['period_covered']} — {i['reason']}", "source_record": "", "sha256": ""})
    for l in case_links(conn, case_id):
        rows.append({"section": "Defect screening", "item": l["defect_id"], "status": R.RESULT_LABELS[l["result"]],
                     "detail": l["explanation"] + (f" Finding: {l['inquiry_finding']}" if l["inquiry_finding"] else ""),
                     "source_record": "", "sha256": ""})
    source_ids = [case["source_record_id"]]
    source_ids += [d["source_record_id"] for d in case_deliveries(conn, case_id)]
    source_ids += [s["source_record_id"] for s in statements(conn, case_id)]
    for sid in source_ids:
        sr = conn.execute("SELECT * FROM source_records WHERE record_id = ?", (sid,)).fetchone()
        if sr:
            rows.append({"section": "Source record", "item": sr["original_id"], "status": sr["source_type"],
                         "detail": f"{sr['source_file']} received {sr['received_at']}",
                         "source_record": sr["record_id"], "sha256": sr["sha256"]})
    for r in case_reviews(conn, case_id):
        rows.append({"section": "Review decision", "item": r["review_id"], "status": r["decision"],
                     "detail": f"{user_name(conn, r['reviewer'])}, {r['recorded_on']}: {r['reasons']}",
                     "source_record": "", "sha256": ""})
    return rows


def case_overview(conn, today: date) -> list[dict]:
    rows = []
    for c in list_cases(conn):
        gate = case_gate(conn, c["case_id"])
        items = evidence_items(conn, c["case_id"])
        tasks = case_tasks(conn, c["case_id"], open_only=True)
        escalations = [task_escalation(t, c, today) for t in tasks]
        top = max(escalations, key=lambda e: R.ESC_SEVERITY[e.level], default=None)
        rows.append({
            "case_id": c["case_id"], "branch": f"{c['branch']} {c['branch_name']}".strip(),
            "status": c["status"].capitalize(), "stage": c["stage"], "gate": gate.state,
            "open_gaps": sum(i["status"] in (R.GAP, R.UNKNOWN) for i in items),
            "open_inquiries": sum(t["required"] for t in tasks),
            "escalation": top.label if top and top.level != R.ESC_NONE else "—",
            "escalation_level": top.level if top else R.ESC_NONE,
            "amount": c["amount"], "period": R.fmt_range(c["disputed_start"], c["disputed_end"]),
            "version": c["horizon_version"],
        })
    return rows


def dashboard_kris(conn, today: date) -> list[dict]:
    """Report Table 4.4 key risk indicators at the demo date."""
    cases = {c["case_id"]: c for c in list_cases(conn)}
    open_tasks = case_tasks(conn, open_only=True)

    def age(created: str) -> int:
        return max(0, R.working_days_between(datetime.strptime(created[:10], "%Y-%m-%d").date(), today))

    # 1. Evidence gaps on active cases
    gaps = [dict(r) for r in conn.execute(
        "SELECT e.* FROM evidence_items e JOIN cases c ON c.case_id = e.case_id"
        " WHERE c.status = 'active' AND e.status IN ('Gap', 'Unknown')")]
    excepted = [g for g in gaps if g["item_type"] in _authorised_exceptions(conn, g["case_id"])]
    oldest_gap = max((age(g["since"]) for g in gaps if g["since"] and g not in excepted), default=0)
    gap_detail = ", ".join(f"{g['case_id']} {g['item_type'].split(' ')[0]} ({age(g['since'])} WD"
                           + (", under exception" if g in excepted else "") + ")" for g in gaps)
    gap_rag = "Red" if oldest_gap >= 20 else "Amber" if oldest_gap >= 10 else "Green"

    # 2. Defect links awaiting a decision
    awaiting = [t for t in open_tasks if t["type"] in ("Defect inquiry", "Manual review")]
    oldest_link = max((age(t["created"]) for t in awaiting), default=0)
    link_rag = "Green" if not awaiting else ("Red" if oldest_link >= 10 else "Amber")

    # 3. Unavailable-evidence exceptions
    exceptions = case_exceptions(conn)
    proposed = [e for e in exceptions if e["status"] == "Proposed"]
    authorised = [e for e in exceptions if e["status"] == "Authorised"]
    attempts = gate_attempts(conn)
    rejected = [a for a in attempts if a["category"].startswith("exception") and a["outcome"] == "Blocked"]
    ex_count = len(proposed) + len(authorised)
    ex_rag = "Green" if ex_count == 0 and not rejected else "Amber" if not rejected else "Red"

    # 4. Closed cases awaiting reassessment
    reassess = [t for t in open_tasks if t["type"] == "Reassessment" and cases[t["case_id"]]["status"] == "closed"]
    oldest_re = max((age(t["created"]) for t in reassess), default=0)
    re_rag = "Green" if not reassess else ("Red" if oldest_re >= 20 else "Amber")

    # 5. Blocked self-review attempts
    self_reviews = [a for a in attempts if a["category"] == "self_review"]
    by_user: dict[str, int] = {}
    for a in self_reviews:
        by_user[a["user"]] = by_user.get(a["user"], 0) + 1
    repeat = [user_name(conn, u) for u, n in by_user.items() if n > 1]

    # 6. Supplier delivery against the evidence schedule
    breaches = []
    for t in case_tasks(conn):
        if t["type"] != "Evidence retrieval" or not t["schedule_due"]:
            continue
        due = date.fromisoformat(t["schedule_due"])
        if t["status"] == "Open" and today > due:
            breaches.append(f"{t['case_id']} {t['task_id']} open past {R.fmt_date(due)}")
        elif t["status"] == "Closed" and t["outcome"] in ("Delivered", "Superseded", RETRIEVAL_UNAVAILABLE):
            closed = datetime.strptime(t["closed_on"], "%Y-%m-%d %H:%M").date()
            if closed > due:
                breaches.append(f"{t['case_id']} {t['task_id']} answered {R.fmt_date(closed)} (due {R.fmt_date(due)})")

    return [
        {"kri": "Evidence gaps on active cases (count and age)", "count": len(gaps),
         "age": f"oldest {oldest_gap} WD" if gaps else "—", "threshold": "Amber at 10; red at 20 working days",
         "escalates_to": "Legal lead, then Audit & Risk Committee", "rag": gap_rag,
         "detail": gap_detail},
        {"kri": "Defect links awaiting a decision", "count": len(awaiting),
         "age": f"oldest {oldest_link} WD" if awaiting else "—", "threshold": "At 10 working days",
         "escalates_to": "Legal lead", "rag": link_rag,
         "detail": ", ".join(f"{t['case_id']} {t['defect_id']} ({t['type'].lower()}, {age(t['created'])} WD)"
                             for t in awaiting)},
        {"kri": "Unavailable-evidence exceptions proposed or authorised", "count": ex_count,
         "age": f"{len(rejected)} rejected attempt(s)" if rejected else "—", "threshold": "Any",
         "escalates_to": "Independent authoriser; legal lead monitors; quarterly Committee summary", "rag": ex_rag,
         "detail": "; ".join([f"{e['exception_id']} {e['case_id']} {e['status'].lower()}" for e in exceptions]
                             + [f"rejected: {a['case_id']} “{a['action']}” by {user_name(conn, a['user'])}"
                                for a in rejected])},
        {"kri": "Closed cases awaiting reassessment", "count": len(reassess),
         "age": f"oldest {oldest_re} WD" if reassess else "—", "threshold": "At 20 working days",
         "escalates_to": "Audit & Risk Committee", "rag": re_rag,
         "detail": ", ".join(f"{t['case_id']} {t['task_id']} ({age(t['created'])} WD)" for t in reassess)},
        {"kri": "Blocked self-review attempts", "count": len(self_reviews),
         "age": f"repeat: {', '.join(repeat)}" if repeat else "—",
         "threshold": "Any attempt; review repeated attempts monthly", "escalates_to": "Internal audit",
         "rag": "Red" if self_reviews else "Green",
         "detail": "; ".join(f"{a['case_id']} by {user_name(conn, a['user'])} on {R.fmt_date(a['ts'])}"
                             for a in self_reviews)},
        {"kri": "Supplier delivery time against the evidence schedule", "count": len(breaches),
         "age": f"schedule {R.SUPPLIER_SCHEDULE_WD} WD", "threshold": "Breach of agreed timescale",
         "escalates_to": "Procurement; legal lead", "rag": "Red" if breaches else "Green",
         "detail": "; ".join(breaches)},
    ]


def open_escalations(conn, today: date) -> list[dict]:
    cases = {c["case_id"]: c for c in list_cases(conn)}
    rows = []
    for t in case_tasks(conn, open_only=True):
        esc = task_escalation(t, cases[t["case_id"]], today)
        if esc.level == R.ESC_NONE:
            continue
        rows.append({"task_id": t["task_id"], "case_id": t["case_id"], "type": t["type"], "title": t["title"],
                     "owner": user_name(conn, t["owner"]), "age_wd": esc.age_wd, "level": esc.level,
                     "escalation": esc.label, "reason": esc.reason})
    return sorted(rows, key=lambda r: (-R.ESC_SEVERITY[r["level"]], -r["age_wd"]))
