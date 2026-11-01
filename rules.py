"""CERT rules engine: Rules 1-5 and the expert completeness check.

Pure functions only. Nothing here touches the database or Streamlit; every
function takes plain values and returns a result that explains itself, so the
same logic is unit-tested and shown to reviewers word for word.

CERT uses transparent rules rather than machine learning, so reviewers can see
exactly why a link was flagged or an action blocked, and because no validated
training dataset exists. A defect link is a reason to inquire, never a finding
of causation; "no match" means no known defect was identified, never that
Horizon was reliable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Mapping, Sequence

UNKNOWN = "Unknown"
ALL_BRANCHES = "ALL"
ONGOING = "Ongoing"

HORIZON_VERSIONS = ("Legacy Horizon", "Horizon Online v1", "Horizon Online v2")

# --- Roles (report Table 4.2) -------------------------------------------------
INVESTIGATOR = "Investigator"
SUPPLIER_LIAISON = "Supplier liaison manager"
TECH_REVIEWER = "Technical reviewer"
LEGAL_REVIEWER = "Independent legal reviewer"
LEGAL_LEAD = "Legal lead (control owner)"
AUDIT = "Internal audit / Audit & Risk Committee"
ROLES = (INVESTIGATOR, SUPPLIER_LIAISON, TECH_REVIEWER, LEGAL_REVIEWER, LEGAL_LEAD, AUDIT)

# Escalation targets
TO_LEGAL_LEAD = "Legal lead"
TO_COMMITTEE = "Audit & Risk Committee"

# --- Rule 1 results -----------------------------------------------------------
LINKED = "Linked"
MANUAL_REVIEW = "Manual review"
NO_MATCH = "No match"
RESULT_LABELS = {
    LINKED: "Potential link – requires inquiry",
    MANUAL_REVIEW: "Manual review – field Unknown",
    NO_MATCH: "No automatic link",
}
NO_KNOWN_DEFECT = "No known defect identified"

# --- Rule 2 evidence checklist ------------------------------------------------
COMPLETE = "Complete"
GAP = "Gap"
NOT_APPLICABLE = "Not applicable"

ARQ = "ARQ audit data"
REMOTE_LOGS = "Remote-intervention logs"
DEFECT_SEARCH = "Defect-search result"
SPM_EXPLANATION = "SPM explanation"
EXPERT_STATEMENT = "Expert statement relied on"
EVIDENCE_ITEMS = (ARQ, REMOTE_LOGS, DEFECT_SEARCH, SPM_EXPLANATION, EXPERT_STATEMENT)
SUPPLIER_ITEMS = (ARQ, REMOTE_LOGS)
ITEM_OWNER_ROLE = {
    ARQ: SUPPLIER_LIAISON,
    REMOTE_LOGS: SUPPLIER_LIAISON,
    DEFECT_SEARCH: INVESTIGATOR,
    SPM_EXPLANATION: INVESTIGATOR,
    EXPERT_STATEMENT: TECH_REVIEWER,
}

DELIVERED = "Delivered"
UNAVAILABLE = "Unavailable"
UNCONFIRMED = "Unconfirmed"

# --- Rule 3 reliance gate -----------------------------------------------------
BLOCKED = "BLOCKED"
CLEAR = "CLEAR"
CLOSED = "CLOSED"

RELY = "Reliance may proceed"
HOLD = "Hold – further inquiry required"
REFER_PROSECUTOR = "Refer to prosecutor for disclosure assessment"
NO_FURTHER_ACTION = "No further action against SPM"
REVIEW_DECISIONS = (HOLD, REFER_PROSECUTOR, NO_FURTHER_ACTION, RELY)

RELIANCE_ACTIONS = (
    "Issue recovery demand",
    "Pass figures on as reliable (prosecution / disclosure)",
)

# --- Rule 4 escalation (proposed service standards, not statutory periods) ----
IMMEDIATE_DEADLINE_WD = 5
ROUTINE_LEGAL_LEAD_WD = 10
ROUTINE_COMMITTEE_WD = 20
SUPPLIER_SCHEDULE_WD = 10

ESC_NONE = "None"
ESC_LEGAL_LEAD = "Legal lead"
ESC_COMMITTEE = "Committee"
ESC_IMMEDIATE = "Immediate"
ESC_SEVERITY = {ESC_NONE: 0, ESC_LEGAL_LEAD: 1, ESC_COMMITTEE: 2, ESC_IMMEDIATE: 3}

# England & Wales bank holidays used by the demo clock (2012-2014).
BANK_HOLIDAYS = frozenset(date.fromisoformat(d) for d in (
    "2012-01-02", "2012-04-06", "2012-04-09", "2012-05-07", "2012-06-04", "2012-06-05",
    "2012-08-27", "2012-12-25", "2012-12-26",
    "2013-01-01", "2013-03-29", "2013-04-01", "2013-05-06", "2013-05-27", "2013-08-26",
    "2013-12-25", "2013-12-26",
    "2014-01-01", "2014-04-18", "2014-04-21", "2014-05-05", "2014-05-26", "2014-08-25",
    "2014-12-25", "2014-12-26",
))


# =============================================================================
# Shared helpers
# =============================================================================

def is_unknown(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == "" or value.strip().lower() == "unknown"
    if isinstance(value, (list, tuple)):
        return len(value) == 0 or any(is_unknown(v) for v in value)
    return False


def parse_date(value):
    """ISO string -> date. Returns None for Unknown and ONGOING for 'Ongoing'."""
    if value is None or isinstance(value, date):
        return value
    text = str(value).strip()
    if text == "" or text.lower() == "unknown":
        return None
    if text.lower() == "ongoing":
        return ONGOING
    return date.fromisoformat(text[:10])


def fmt_date(value) -> str:
    d = parse_date(value)
    if d is None:
        return UNKNOWN
    if d == ONGOING:
        return ONGOING
    return f"{d.day} {d:%b %Y}"


def fmt_range(start, end) -> str:
    s, e = parse_date(start), parse_date(end)
    if isinstance(s, date) and isinstance(e, date) and s.year == e.year:
        return f"{s.day} {s:%b} – {fmt_date(e)}"
    return f"{fmt_date(s)} – {fmt_date(e)}"


def span_text(days: int) -> str:
    if days % 7 == 0:
        weeks = days // 7
        return f"{weeks} week{'s' if weeks != 1 else ''}"
    return f"{days} day{'s' if days != 1 else ''}"


def portion_text(part: int, total: int) -> str:
    if part % 7 == 0 and total % 7 == 0:
        return f"{part // 7} of {total // 7} weeks"
    return f"{part} of {total} days"


def as_scope(value):
    """Normalise a branch or version scope to ALL_BRANCHES, None (Unknown) or a tuple."""
    if isinstance(value, str):
        text = value.strip()
        if text.upper() == ALL_BRANCHES:
            return ALL_BRANCHES
        if is_unknown(text):
            return None
        return tuple(p.strip() for p in text.replace(",", ";").split(";") if p.strip())
    if value is None:
        return None
    items = tuple(str(v).strip() for v in value)
    if any(v.upper() == ALL_BRANCHES for v in items):
        return ALL_BRANCHES
    if not items or any(is_unknown(v) for v in items):
        return None
    return items


# =============================================================================
# Working days (used by Rule 4)
# =============================================================================

def is_working_day(d: date) -> bool:
    return d.weekday() < 5 and d not in BANK_HOLIDAYS


def working_days_between(start: date, end: date) -> int:
    """Working days after `start` up to and including `end` (negative if end < start)."""
    if end == start:
        return 0
    sign, lo, hi = (1, start, end) if end > start else (-1, end, start)
    count, d = 0, lo + timedelta(days=1)
    while d <= hi:
        if is_working_day(d):
            count += 1
        d += timedelta(days=1)
    return sign * count


def add_working_days(start: date, n: int) -> date:
    d, added = start, 0
    while added < n:
        d += timedelta(days=1)
        if is_working_day(d):
            added += 1
    return d


# =============================================================================
# Rule 1 – Defect linking
# =============================================================================

@dataclass(frozen=True)
class LinkResult:
    result: str
    matched_fields: tuple[str, ...]
    unknown_fields: tuple[str, ...]
    failed_fields: tuple[str, ...]
    explanation: str

    @property
    def flagged(self) -> bool:
        return self.result in (LINKED, MANUAL_REVIEW)


def _branch_check(case_branch, scope_value):
    scope = as_scope(scope_value)
    if is_unknown(case_branch):
        return None, "case branch is Unknown"
    if scope is None:
        return None, "defect branch scope is Unknown"
    if scope == ALL_BRANCHES:
        return True, "defect scope covers all branches"
    if str(case_branch) in scope:
        return True, f"branch {case_branch} is within the defect's scope"
    return False, f"branch {case_branch} is outside the defect's scope ({', '.join(scope)})"


def _period_check(disputed_start, disputed_end, affected_start, affected_end):
    ds, de = parse_date(disputed_start), parse_date(disputed_end)
    a_s, a_e = parse_date(affected_start), parse_date(affected_end)
    if ds is None or de is None:
        return None, "the disputed period is Unknown"
    if a_e == ONGOING:
        a_e = date.max
    if isinstance(a_s, date) and a_s > de:
        return False, (f"affected period ({fmt_range(affected_start, affected_end)}) begins after "
                       f"the disputed period ({fmt_range(ds, de)})")
    if isinstance(a_e, date) and a_e < ds:
        return False, (f"affected period ({fmt_range(affected_start, affected_end)}) does not overlap "
                       f"the disputed period ({fmt_range(ds, de)})")
    if a_s is None:
        return None, "the defect's affected start date is Unknown"
    if a_e is None:
        return None, "the defect's affected end date is Unknown"
    return True, (f"affected period {fmt_range(affected_start, affected_end)} overlaps the disputed "
                  f"period {fmt_range(ds, de)}")


def _version_check(case_version, versions_value):
    versions = as_scope(versions_value)
    if is_unknown(case_version):
        return None, "the case's Horizon version is Unknown"
    if versions is None:
        return None, "the defect's affected versions are Unknown"
    if versions == ALL_BRANCHES:
        return True, "defect affects all Horizon versions"
    if case_version in versions:
        return True, f"{case_version} is an affected version"
    return False, (f"different Horizon version (defect affects {', '.join(versions)}; "
                   f"case recorded on {case_version})")


def match_defect(case: Mapping, defect: Mapping) -> LinkResult:
    """Rule 1. Flag a potential link only when branch, affected period and version all hold.

    Uses the defect's *affected* period, not its reported date, so a defect
    discovered later still links to earlier cases. Any Unknown field sends the
    pair to the manual-review queue; nothing is discarded.
    """
    checks = {
        "branch": _branch_check(case.get("branch"), defect.get("affected_branches")),
        "affected period": _period_check(case.get("disputed_start"), case.get("disputed_end"),
                                         defect.get("affected_start"), defect.get("affected_end")),
        "version": _version_check(case.get("horizon_version"), defect.get("versions")),
    }
    matched = tuple(k for k, (ok, _) in checks.items() if ok is True)
    unknown = tuple(k for k, (ok, _) in checks.items() if ok is None)
    failed = tuple(k for k, (ok, _) in checks.items() if ok is False)
    did = defect.get("defect_id", "defect")

    if failed:
        reasons = "; ".join(checks[k][1] for k in failed)
        explanation = (f"No automatic link to {did}: {reasons}. "
                       "An explained manual assessment remains possible.")
        return LinkResult(NO_MATCH, matched, unknown, failed, _capitalise(explanation))

    if unknown:
        reasons = "; ".join(checks[k][1] for k in unknown)
        held = "; ".join(checks[k][1] for k in matched)
        explanation = (f"Sent to the manual-review queue: {reasons}, so a link to {did} cannot be "
                       f"confirmed or excluded.")
        if held:
            explanation += f" Fields that do match: {held}."
        explanation += " The pair is kept for a person to decide, never discarded."
        return LinkResult(MANUAL_REVIEW, matched, unknown, failed, explanation)

    reasons = "; ".join(checks[k][1] for k in matched)
    explanation = f"Potential link to {did} requiring inquiry: {reasons}."
    reported = parse_date(defect.get("date_reported"))
    disputed_end = parse_date(case.get("disputed_end"))
    if isinstance(reported, date) and isinstance(disputed_end, date) and reported > disputed_end:
        explanation += (f" The defect was reported on {fmt_date(reported)}, after the disputed period; "
                        "matching uses the affected period, not the report date.")
    explanation += " A link justifies inquiry; it does not establish causation."
    return LinkResult(LINKED, matched, unknown, failed, explanation)


def _capitalise(text: str) -> str:
    return text[:1].upper() + text[1:]


# =============================================================================
# Rule 2 – Evidence coverage and the expert completeness check
# =============================================================================

@dataclass(frozen=True)
class Coverage:
    total_days: int
    covered_days: int
    missing: tuple[tuple[date, date], ...]

    @property
    def complete(self) -> bool:
        return not self.missing


@dataclass(frozen=True)
class EvidenceAssessment:
    item_type: str
    status: str
    period_covered: str
    reason: str
    missing: tuple[tuple[date, date], ...] = ()


def period_coverage(start: date, end: date, delivered: Iterable[tuple[date, date]]) -> Coverage:
    """Days of [start, end] covered by the union of delivered periods, and the gaps left."""
    total = (end - start).days + 1
    covered = set()
    for s, e in delivered:
        s, e = max(s, start), min(e, end)
        d = s
        while d <= e:
            covered.add(d)
            d += timedelta(days=1)
    missing, run_start, d = [], None, start
    while d <= end:
        if d not in covered and run_start is None:
            run_start = d
        if d in covered and run_start is not None:
            missing.append((run_start, d - timedelta(days=1)))
            run_start = None
        d += timedelta(days=1)
    if run_start is not None:
        missing.append((run_start, end))
    return Coverage(total, len(covered), tuple(missing))


def assess_supplier_item(item_type: str, disputed_start, disputed_end,
                         deliveries: Sequence[Mapping]) -> EvidenceAssessment:
    """Rule 2 for supplier-held records. Partial coverage of the disputed period is a Gap."""
    ds, de = parse_date(disputed_start), parse_date(disputed_end)
    if not isinstance(ds, date) or not isinstance(de, date):
        return EvidenceAssessment(item_type, UNKNOWN, UNKNOWN,
                                  "Disputed period is Unknown, so coverage cannot be assessed")
    delivered = [(parse_date(d["period_start"]), parse_date(d["period_end"]))
                 for d in deliveries if d.get("availability") == DELIVERED]
    cov = period_coverage(ds, de, delivered)
    unconfirmed = any(d.get("availability") == UNCONFIRMED for d in deliveries)
    unavailable = any(d.get("availability") == UNAVAILABLE for d in deliveries)
    portion = portion_text(cov.covered_days, cov.total_days)

    if cov.complete:
        return EvidenceAssessment(item_type, COMPLETE, f"{fmt_range(ds, de)} ({portion})",
                                  "Full disputed period received")
    missing = ", ".join(fmt_range(s, e) for s, e in cov.missing)
    covered = "None received" if cov.covered_days == 0 else portion
    if cov.covered_days == 0 and unconfirmed:
        return EvidenceAssessment(item_type, UNKNOWN, covered,
                                  "Supplier has not confirmed whether these records exist for the "
                                  "disputed period", cov.missing)
    reason = f"{portion} received; missing {missing}"
    if unavailable:
        reason += " (supplier reports the missing records unavailable)"
    return EvidenceAssessment(item_type, GAP, covered, reason, cov.missing)


def assess_defect_search(links: Sequence[Mapping], defects_screened: int) -> EvidenceAssessment:
    pending = sorted(l["defect_id"] for l in links
                     if l["result"] == MANUAL_REVIEW and l.get("inquiry_status") == "Open")
    flagged = sorted(l["defect_id"] for l in links if l["result"] == LINKED)
    scope = f"Screened against {defects_screened} defect record{'s' if defects_screened != 1 else ''}"
    if pending:
        return EvidenceAssessment(DEFECT_SEARCH, UNKNOWN, scope,
                                  f"Manual review pending for {', '.join(pending)} (a required field is Unknown)")
    if flagged:
        return EvidenceAssessment(DEFECT_SEARCH, COMPLETE, scope,
                                  f"Potential links requiring inquiry: {', '.join(flagged)}")
    return EvidenceAssessment(DEFECT_SEARCH, COMPLETE, scope,
                              f"{NO_KNOWN_DEFECT} (not confirmation that Horizon was reliable)")


def assess_spm_explanation(text) -> EvidenceAssessment:
    if text and str(text).strip():
        return EvidenceAssessment(SPM_EXPLANATION, COMPLETE, "Recorded", "SPM's account recorded and preserved")
    return EvidenceAssessment(SPM_EXPLANATION, GAP, "Not recorded",
                              "No SPM explanation recorded; the SPM's account must be sought")


def expert_completeness(statement_defects: Iterable[str], relevant_defects: Iterable[str]) -> list[str]:
    """Relevant linked PEAKs/KELs that the expert statement does not address."""
    addressed = set(statement_defects)
    return sorted(d for d in set(relevant_defects) if d not in addressed)


def assess_expert_item(statement: Mapping | None, check: Mapping | None,
                       relevant_defects: Sequence[str]) -> EvidenceAssessment:
    if statement is None:
        return EvidenceAssessment(EXPERT_STATEMENT, NOT_APPLICABLE, "None relied on",
                                  "No expert statement is relied on")
    label = f"{statement['statement_id']} v{statement['version']} ({statement['author']})"
    if check is None:
        return EvidenceAssessment(EXPERT_STATEMENT, UNKNOWN, label,
                                  "Not yet checked against linked PEAKs/KELs by a technical reviewer")
    if set(check["relevant_defects"]) != set(relevant_defects):
        new = sorted(set(relevant_defects) - set(check["relevant_defects"]))
        extra = f" (newly linked: {', '.join(new)})" if new else ""
        return EvidenceAssessment(EXPERT_STATEMENT, UNKNOWN, label,
                                  f"Linked defects changed since the last check{extra}; check must be repeated")
    if check["omissions"]:
        return EvidenceAssessment(EXPERT_STATEMENT, GAP, label,
                                  f"Statement omits {', '.join(check['omissions'])}; correction requested "
                                  "and independent assessment required")
    checked = ", ".join(relevant_defects) if relevant_defects else "no linked defects"
    return EvidenceAssessment(EXPERT_STATEMENT, COMPLETE, label,
                              f"Checked against {checked}; no omissions recorded")


# =============================================================================
# Rule 3 – Reliance gate, independence and exceptions
# =============================================================================

@dataclass
class GateResult:
    state: str
    reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return self.state != CLEAR


def evaluate_gate(*, status: str, evidence: Sequence[Mapping], open_required: Sequence[Mapping],
                  review: Mapping | None, evidence_version: int,
                  authorised_exceptions: Mapping[str, str], include_review: bool = True) -> GateResult:
    """Rule 3. Reliance on disputed figures is BLOCKED unless every condition holds.

    Returns every reason so the banner can state why. An authorised exception
    never hides a gap and never overrides an open required inquiry.
    """
    if status == "closed":
        reassess = [t for t in open_required if t["type"] == "Reassessment"]
        if not reassess:
            return GateResult(CLOSED, notes=["Case closed; no reassessment open."])
        reasons = ["Closed case under reassessment: further reliance on the original figures "
                   "(e.g. continued recovery) is suspended until the reassessment is decided"]
        reasons += [f"Open reassessment {t['task_id']}: {t['title']} (owner {t['owner']})" for t in reassess]
        return GateResult(BLOCKED, reasons)

    reasons, notes = [], []
    shown_items = set()
    follow_ups = {t["item_type"]: t for t in open_required if t.get("item_type")}
    for item in evidence:
        if item["status"] not in (GAP, UNKNOWN):
            continue
        item_type = item["item_type"]
        task = follow_ups.get(item_type)
        exception_id = authorised_exceptions.get(item_type)
        if exception_id and not task:
            notes.append(f"{item_type} — {item['status']} remains visible: {item['reason']}. "
                         f"Reliance only under authorised exception {exception_id}.")
            continue
        line = f"{item_type} — {item['status']}: {item['reason']}"
        if task:
            line += f" (follow-up {task['task_id']} with {task['owner']})"
        reasons.append(line)
        shown_items.add(item_type)
    for task in open_required:
        if task.get("item_type") in shown_items:
            continue
        reasons.append(f"Open required inquiry {task['task_id']}: {task['title']} (owner {task['owner']})")

    if include_review:
        if review is None:
            reasons.append("No independent review recorded: a reviewer with no prior involvement "
                           "must record a reasoned decision")
        elif review["evidence_version"] != evidence_version:
            reasons.append(f"Independent review {review['review_id']} was based on evidence "
                           f"v{review['evidence_version']}; evidence is now v{evidence_version}, "
                           "so a fresh review is required")
        elif review["decision"] != RELY:
            reasons.append(f"Independent review {review['review_id']} ({review['reviewer']}, "
                           f"{fmt_date(review['recorded_on'])}) decided “{review['decision']}”, "
                           "which does not permit reliance")
    if reasons:
        return GateResult(BLOCKED, reasons, notes)
    if include_review and review is not None:
        notes.insert(0, f"Independent review {review['review_id']} by {review['reviewer']} on "
                        f"{fmt_date(review['recorded_on'])} (evidence v{review['evidence_version']}) "
                        "permits reliance.")
    return GateResult(CLEAR, [], notes)


def review_problems(*, reviewer_id: str, reviewer_name: str, reviewer_role: str,
                    involved_users: Iterable[str], declared_no_involvement: bool,
                    reasons: str) -> tuple[list[str], bool]:
    """Independence checks on a review submission. Returns (problems, is_self_review)."""
    problems = []
    self_review = reviewer_id in set(involved_users)
    if self_review:
        problems.append(f"Self-approval blocked: {reviewer_name} is recorded as involved in this case")
    if reviewer_role != LEGAL_REVIEWER:
        problems.append(f"The role “{reviewer_role}” cannot record an independent review")
    if not declared_no_involvement:
        problems.append("No conflict declaration: the reviewer must declare no prior involvement")
    if not (reasons or "").strip():
        problems.append("Reasons are required for every review decision")
    return problems, self_review


def exception_proposal_problems(*, proposer_id: str, proposer_name: str, proposer_role: str,
                                involved_users: Iterable[str], item_type: str, item_status: str,
                                retrieval_exhausted: bool, open_required: Sequence[Mapping],
                                implications: str, proposed_action: str, reasons: str,
                                duties_confirmed: bool) -> list[str]:
    """An unavailable-evidence exception may only follow documented reasonable retrieval."""
    problems = []
    if open_required:
        ids = ", ".join(t["task_id"] for t in open_required)
        problems.append(f"An exception cannot bypass an open required inquiry ({ids})")
    if item_status not in (GAP, UNKNOWN):
        problems.append(f"{item_type} is {item_status}; exceptions apply only to evidence that is unavailable")
    if not retrieval_exhausted:
        problems.append("Reasonable retrieval is not documented: the retrieval request must first be "
                        "closed as unavailable, with the steps taken")
    if proposer_role != LEGAL_REVIEWER:
        problems.append(f"The role “{proposer_role}” cannot propose an exception")
    if proposer_id in set(involved_users):
        problems.append(f"{proposer_name} is recorded as involved in this case")
    if not all((text or "").strip() for text in (implications, proposed_action, reasons)):
        problems.append("The gap's implications, the proposed action and the reasons must all be recorded")
    if not duties_confirmed:
        problems.append("Confirmation that applicable duties (disclosure, reasonable inquiry) are met is required")
    return problems


def exception_authorisation_problems(*, authoriser_id: str, authoriser_name: str, authoriser_role: str,
                                     authoriser_external: bool, proposer_id: str,
                                     involved_users: Iterable[str], open_required: Sequence[Mapping],
                                     independence_confirmed: bool) -> list[str]:
    """Separate authorisation by an uninvolved legal lead or external legal reviewer."""
    problems = []
    eligible = authoriser_role == LEGAL_LEAD or (authoriser_role == LEGAL_REVIEWER and authoriser_external)
    if not eligible:
        problems.append("Only an uninvolved legal lead or an external legal reviewer may authorise an exception")
    if authoriser_id == proposer_id:
        problems.append("Authorisation must be separate from the person who proposed the exception")
    if authoriser_id in set(involved_users):
        problems.append(f"Conflicted authoriser: {authoriser_name} is recorded as involved in this case")
    if open_required:
        ids = ", ".join(t["task_id"] for t in open_required)
        problems.append(f"An exception cannot bypass an open required inquiry ({ids})")
    if not independence_confirmed:
        problems.append("The authoriser must confirm no prior involvement in the case")
    return problems


# =============================================================================
# Rule 4 – Escalation (working days on the demo clock)
# =============================================================================

@dataclass(frozen=True)
class Escalation:
    level: str
    targets: tuple[str, ...]
    age_wd: int
    reason: str

    @property
    def label(self) -> str:
        if self.level == ESC_NONE:
            return "—"
        if self.level == ESC_IMMEDIATE:
            text = f"Immediate → {self.targets[0]}"
            if TO_COMMITTEE in self.targets[1:]:
                text += "; 20 WD → Committee"
            return text
        if self.level == ESC_COMMITTEE:
            return "20 WD → Audit & Risk Committee"
        return "10 WD → Legal lead"


def assess_escalation(created: date, today: date, *, urgent: bool = False,
                      legal_deadline: date | None = None,
                      immediate_target: str = TO_LEGAL_LEAD) -> Escalation:
    """Rule 4. Undermining material or a legal deadline within 5 working days escalates
    immediately; routine delay escalates to the legal lead at 10 and the Committee at 20
    working days. These are proposed service standards, not statutory periods."""
    age = max(0, working_days_between(created, today))
    reasons, targets = [], []
    immediate = False
    if urgent:
        immediate = True
        reasons.append("material may undermine an active case or a control was breached")
    if legal_deadline is not None:
        left = working_days_between(today, legal_deadline)
        if left <= IMMEDIATE_DEADLINE_WD:
            immediate = True
            if left < 0:
                reasons.append(f"legal deadline {fmt_date(legal_deadline)} has passed")
            else:
                reasons.append(f"legal deadline {fmt_date(legal_deadline)} is {left} working day"
                               f"{'s' if left != 1 else ''} away")
    routine = None
    if age >= ROUTINE_COMMITTEE_WD:
        routine = TO_COMMITTEE
    elif age >= ROUTINE_LEGAL_LEAD_WD:
        routine = TO_LEGAL_LEAD
    if routine:
        reasons.append(f"open {age} working days (routine thresholds 10 / 20)")
    if immediate:
        targets.append(immediate_target)
    if routine and routine not in targets:
        targets.append(routine)

    if immediate:
        level = ESC_IMMEDIATE
    elif routine == TO_COMMITTEE:
        level = ESC_COMMITTEE
    elif routine == TO_LEGAL_LEAD:
        level = ESC_LEGAL_LEAD
    else:
        level = ESC_NONE
    reason = "; ".join(reasons) if reasons else f"open {age} working days; within service standard"
    return Escalation(level, tuple(targets), age, _capitalise(reason))


# =============================================================================
# Rule 5 – Reassessment on new or updated defect records
# =============================================================================

@dataclass(frozen=True)
class ScreeningAction:
    case_id: str
    link: LinkResult
    previous_result: str | None
    newly_flagged: bool
    withdrawn: bool
    create_inquiry: bool
    create_reassessment: bool
    original_decision: str | None


def plan_reassessment(defect: Mapping, cases: Sequence[Mapping],
                      previous_results: Mapping[str, str]) -> list[ScreeningAction]:
    """Rule 5. Re-run Rule 1 for a new or updated defect against every case, open and
    closed, regardless of date. Cases with an earlier decision get a reassessment task
    that preserves the original decision; nothing is overwritten."""
    actions = []
    for case in cases:
        link = match_defect(case, defect)
        previous = previous_results.get(case["case_id"])
        newly = link.flagged and previous != link.result
        withdrawn = previous in (LINKED, MANUAL_REVIEW) and not link.flagged
        closed = case.get("status") == "closed"
        decision = case.get("latest_decision_id")
        actions.append(ScreeningAction(
            case_id=case["case_id"], link=link, previous_result=previous,
            newly_flagged=newly, withdrawn=withdrawn,
            create_inquiry=(newly or withdrawn) and not closed,
            create_reassessment=newly and (closed or decision is not None),
            original_decision=decision,
        ))
    return actions
