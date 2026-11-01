"""Run the Table 4.6 tests, compute the Section 4.2.7 metrics and write test_results.md.

    python evaluation.py

Recall and precision are measured against GROUND_TRUTH_RELEVANT in seed.py after
the later defect record (KEL-D07) is loaded. Gate enforcement replays every
prohibited action we could construct on the seeded cases and counts how many
the rules engine blocked. These are design checks on synthetic data; they
cannot establish real-world accuracy.
"""
from __future__ import annotations

import platform
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import db
import rules as R
import seed
import services as S

ROOT = Path(__file__).parent
TABLE_4_6 = [
    ("test_01", "Relevant defect with overlapping affected period", "Link flagged; documented inquiry required"),
    ("test_02", "Unrelated branch or incompatible version", "No automatic link; explained manual assessment possible"),
    ("test_03", "Missing audit period or unknown field", "Gap or uncertainty shown; follow-up task assigned"),
    ("test_04", "Defect learned after a decision", "Reassessment tasks created for closed and earlier cases"),
    ("test_05", "Self-approval or open inquiry at reliance gate", "Approval blocked and reason recorded"),
    ("test_06", "Overdue request or imminent deadline", "Correct routine or immediate escalation generated"),
    ("test_07", "Expert statement omits a relevant known defect",
     "Record omission; require correction and independent assessment; keep gate blocked"),
    ("test_08", "Unavailable evidence after reasonable retrieval",
     "Retain gap; require action-specific reasons and separate authorisation"),
    ("test_09", "Exception attempted with an open inquiry or conflicted authoriser",
     "Reject exception; record attempt and escalate"),
]


def _pct(num: int, den: int) -> dict:
    return {"value": (num / den) if den else 0.0, "num": num, "den": den}


def gate_battery(conn) -> list[dict]:
    """Attempt every prohibited action we can construct on the seed; also run permitted controls."""
    now = datetime.combine(seed.DEMO_DATE, datetime.min.time()).replace(hour=12)
    users = {u.user_id: u for u in S.list_users(conn)}
    rows: list[dict] = []

    def run(scenario: str, prohibited: bool, outcome: S.Outcome) -> None:
        rows.append({"scenario": scenario, "prohibited": prohibited, "blocked": not outcome.ok,
                     "reason": (outcome.problems or [outcome.message])[0]})

    permitted_later = []
    for case in S.list_cases(conn):
        cid = case["case_id"]
        gate = S.case_gate(conn, cid)
        action = R.RELIANCE_ACTIONS[0]
        if gate.state == R.CLEAR:
            permitted_later.append((f"{cid}: {action} with gate CLEAR", cid, action))
        else:
            run(f"{cid}: {action} while gate {gate.state}", True,
                S.attempt_reliance(conn, users["u_tan"], now, cid, action))
            run(f"{cid}: {R.RELIANCE_ACTIONS[1]} while gate {gate.state}", True,
                S.attempt_reliance(conn, users["u_tan"], now, cid, R.RELIANCE_ACTIONS[1]))
        if case["status"] != "active":
            continue
        for uid in case["involved_users"]:
            run(f"{cid}: self-approval by involved {users[uid].name}", True,
                S.record_review(conn, users[uid], now, cid, declared_no_involvement=True,
                                decision=R.RELY, reasons="Proceed."))
        if S.case_gate(conn, cid, include_review=False).blocked:
            reviewer = next(u for u in ("u_wong", "u_lim", "u_clarke") if u not in case["involved_users"])
            run(f"{cid}: “{R.RELY}” by uninvolved {users[reviewer].name} while blockers remain", True,
                S.record_review(conn, users[reviewer], now, cid, declared_no_involvement=True,
                                decision=R.RELY, reasons="Proceed."))
        if S._gate_inputs(conn, case)["open_required"]:
            proposer = next(u for u in ("u_lim", "u_wong") if u not in case["involved_users"])
            run(f"{cid}: exception proposed while a required inquiry is open", True,
                S.propose_exception(conn, users[proposer], now, cid, item_type=R.ARQ,
                                    implications="Untested period.", proposed_action="Proceed.",
                                    reasons="Delay.", duties_confirmed=True))
    run("C005: review recorded by uninvolved investigator A. Tan (role not authorised)", True,
        S.record_review(conn, users["u_tan"], now, "C005", declared_no_involvement=True,
                        decision=R.HOLD, reasons="Hold."))
    run("C005: reviewer omits the conflict declaration", True,
        S.record_review(conn, users["u_wong"], now, "C005", declared_no_involvement=False,
                        decision=R.RELY, reasons="Proceed."))
    run("C010: EX-002 authorised by conflicted legal lead D. Morgan", True,
        S.authorise_exception(conn, users["u_morgan"], now, "EX-002", independence_confirmed=True))
    run("C010: EX-002 authorised by its proposer K. Wong", True,
        S.authorise_exception(conn, users["u_wong"], now, "EX-002", independence_confirmed=True))

    for scenario, cid, action in permitted_later:
        run(scenario, False, S.attempt_reliance(conn, users["u_tan"], now, cid, action))
    run("C010: EX-002 authorised by uninvolved external reviewer E. Clarke", False,
        S.authorise_exception(conn, users["u_clarke"], now, "EX-002", independence_confirmed=True))
    return rows


def compute_metrics(workdir: str | Path) -> dict:
    path = seed.build(Path(workdir) / "metrics.db")
    conn = db.connect(path)
    now = datetime.combine(seed.DEMO_DATE, datetime.min.time()).replace(hour=11)

    def flagged_pairs() -> set[tuple[str, str]]:
        return {(r["case_id"], r["defect_id"]) for r in conn.execute(
            "SELECT case_id, defect_id FROM defect_links WHERE result IN (?, ?)", (R.LINKED, R.MANUAL_REVIEW))}

    seed_flags = flagged_pairs()
    seed_truth = {p for p in seed.GROUND_TRUTH_RELEVANT if p[1] != "KEL-D07"}
    S.load_defect(conn, S.get_actor(conn, "u_okafor"), now, seed.SAMPLE_LATER_DEFECT)
    flags = flagged_pairs()
    truth = seed.GROUND_TRUTH_RELEVANT
    hits = flags & truth

    battery = gate_battery(conn)
    prohibited = [r for r in battery if r["prohibited"]]
    permitted = [r for r in battery if not r["prohibited"]]
    conn.close()
    return {
        "recall": _pct(len(hits), len(truth)),
        "precision": _pct(len(hits), len(flags)),
        "seed_recall": _pct(len(seed_flags & seed_truth), len(seed_truth)),
        "seed_precision": _pct(len(seed_flags & seed_truth), len(seed_flags)),
        "false_flags": sorted(flags - truth),
        "missed": sorted(truth - flags),
        "gate_enforcement": _pct(sum(r["blocked"] for r in prohibited), len(prohibited)),
        "permitted_allowed": _pct(sum(not r["blocked"] for r in permitted), len(permitted)),
        "battery": battery,
    }


class _Collector:
    def __init__(self):
        self.results: dict[str, dict] = {}

    def pytest_runtest_logreport(self, report):
        if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
            name = report.nodeid.split("::")[-1]
            self.results[name] = {
                "file": report.nodeid.split("::")[0], "outcome": report.outcome,
                "observed": " ".join(v for k, v in report.user_properties if k == "observed"),
                "error": str(report.longrepr).splitlines()[-1] if report.failed else "",
            }


def _fmt(p: dict) -> str:
    return f"{p['value']:.0%} ({p['num']}/{p['den']})"


def write_report(results: dict, metrics: dict, path: Path) -> None:
    import pytest  # noqa: F401  (version only)
    lines = [
        "# CERT – Test results (report Table 4.6 and Section 4.2.7)", "",
        f"Generated {datetime.now():%d %b %Y %H:%M} by `python evaluation.py` · Python "
        f"{platform.python_version()} · pytest {sys.modules['pytest'].__version__} · demo date "
        f"{R.fmt_date(seed.DEMO_DATE)} · synthetic data only.", "",
        "## Table 4.6 – Test conditions, expected and observed outcomes", "",
        "| # | Test condition | Expected outcome | Observed outcome (synthetic data) | Result |",
        "|---|---|---|---|---|",
    ]
    for i, (prefix, condition, expected) in enumerate(TABLE_4_6, 1):
        key = next((k for k in results if k.startswith(prefix)), None)
        r = results.get(key, {"outcome": "not run", "observed": "", "error": ""})
        observed = r["observed"] or r["error"]
        lines.append(f"| {i} | {condition} | {expected} | {observed} | **{r['outcome'].upper()}** |")

    lines += [
        "", "## Effectiveness metrics", "",
        "| Metric | Target | Result | Notes |", "|---|---|---|---|",
        f"| Recall (seeded relevant links flagged) | 100% | {_fmt(metrics['recall'])} | After Rule 5 loads KEL-D07; "
        f"seed alone {_fmt(metrics['seed_recall'])}. Manual-review items count as flagged. |",
        f"| Precision (flags judged relevant) | Monitored, no target | {_fmt(metrics['precision'])} | Not relevant: "
        + ", ".join(f"{c} ↔ {d}" for c, d in metrics["false_flags"])
        + " (cosmetic print defect; matched on scope, period and version, then closed on inquiry). "
        f"Seed alone {_fmt(metrics['seed_precision'])}. |",
        f"| Gate enforcement (prohibited actions blocked) | 100% | {_fmt(metrics['gate_enforcement'])} | "
        "Every blocked attempt is logged in `gate_attempts` and the audit log. |",
        f"| Permitted actions allowed (control) | — | {_fmt(metrics['permitted_allowed'])} | Shows the gate is not "
        "simply blocking everything. |",
        "| Review time; alerts per reviewer per week | — | Not measured | Needs real reviewers in a pilot. |",
        "", "## Gate-enforcement battery", "",
        "| Scenario | Prohibited? | Outcome | First reason recorded |", "|---|---|---|---|",
    ]
    for r in metrics["battery"]:
        outcome = "Blocked" if r["blocked"] else "Permitted"
        reason = r["reason"].replace("|", "/")
        lines.append(f"| {r['scenario']} | {'Yes' if r['prohibited'] else 'No'} | {outcome} | {reason} |")

    others = {k: v for k, v in results.items() if not any(k.startswith(p) for p, _, _ in TABLE_4_6)}
    lines += ["", "## Supporting tests", "", "| Test | Result |", "|---|---|"]
    lines += [f"| `{k}` | **{v['outcome'].upper()}** |" for k, v in others.items()]
    lines += [
        "", "## Interpretation", "",
        "These targets are design standards, not legal thresholds. The cases, defects and expected links were "
        "written by the project team, so the results show that the rules behave as specified; they cannot "
        "establish accuracy on real PEAKs, KELs or case files. A pilot would add review time, alert volume per "
        "reviewer and audit sampling of closed flags, exceptions and no-match cases.", "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    import pytest
    collector = _Collector()
    code = pytest.main(["-q", str(ROOT / "tests"), "-p", "no:cacheprovider"], plugins=[collector])
    with tempfile.TemporaryDirectory() as tmp:
        metrics = compute_metrics(tmp)
    write_report(collector.results, metrics, ROOT / "test_results.md")
    print(f"\nRecall {_fmt(metrics['recall'])} · Precision {_fmt(metrics['precision'])} · "
          f"Gate enforcement {_fmt(metrics['gate_enforcement'])} · wrote test_results.md")
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
