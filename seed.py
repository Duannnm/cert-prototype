"""Synthetic demonstration data for CERT. Every person, branch and record is fictional.

The seed is not a static dump: it replays a dated timeline through the same
service functions the app uses, so every link, task, escalation and audit-log
entry is produced by the rules engine itself. The demo clock then defaults to
DEMO_DATE.

Case C014 reproduces report Section 4.2.6. The later defect record (KEL-D07)
is deliberately left out so Rule 5 can be shown live from the Defect records
page; SAMPLE_LATER_DEFECT holds it.
"""
from __future__ import annotations

import os
import sys
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

import db
import rules as R
import services as S

DEMO_DATE = date(2013, 11, 18)

USERS = [
    ("u_tan", "A. Tan", R.INVESTIGATOR, 0, None),
    ("u_shah", "R. Shah", R.INVESTIGATOR, 0, None),
    ("u_okafor", "M. Okafor", R.SUPPLIER_LIAISON, 0, None),
    ("u_patel", "S. Patel", R.TECH_REVIEWER, 0, None),
    ("u_lim", "J. Lim", R.LEGAL_REVIEWER, 0, "In-house, independent of investigations"),
    ("u_wong", "K. Wong", R.LEGAL_REVIEWER, 0, "In-house, independent of investigations"),
    ("u_clarke", "E. Clarke", R.LEGAL_REVIEWER, 1, "External legal reviewer"),
    ("u_morgan", "D. Morgan", R.LEGAL_LEAD, 0, "Owns the review policy and CERT's rules"),
    ("u_ng", "H. Ng", R.AUDIT, 0, "Internal audit; reports to the Audit & Risk Committee"),
    ("u_chen", "L. Chen", R.COMMITTEE, 0, "Committee oversight and escalations"),
    ("u_evans", "P. Evans", R.OVERSEER, 1, "Read-only oversight of all synthetic cases in this demo"),
]

HO2 = "Horizon Online v2"

DEFECTS = {
    "PEAK-P03": dict(defect_id="PEAK-P03", type="PEAK", affected_branches="088",
                     affected_start="2012-09-03", affected_end="2012-12-14",
                     versions="Horizon Online v1;Horizon Online v2",
                     symptoms="Remote data correction applied to branch transactions without a branch-visible record",
                     date_reported="2012-12-20"),
    "KEL-D02": dict(defect_id="KEL-D02", type="KEL", affected_branches="101;156;214;233",
                    affected_start="2012-11-01", affected_end="2013-08-30", versions="Legacy Horizon",
                    symptoms="Counter freeze during cash declaration duplicates the declared amount",
                    date_reported="2013-02-11"),
    "PEAK-P08": dict(defect_id="PEAK-P08", type="PEAK", affected_branches="ALL",
                     affected_start="2013-08-01", affected_end="2013-10-31", versions=HO2,
                     symptoms="Branch trading statement prints with misaligned columns; underlying figures unaffected",
                     date_reported="2013-09-23"),
    "KEL-D05": dict(defect_id="KEL-D05", type="KEL", affected_branches="042;117",
                    affected_start="2007-01-08", affected_end="2010-03-31", versions="Legacy Horizon",
                    symptoms="Transfer between stock units recorded twice after a communications failure",
                    date_reported="2013-10-07"),
    "KEL-D01": dict(defect_id="KEL-D01", type="KEL", affected_branches="214;305",
                    affected_start="2013-03-18", affected_end="2013-06-28", versions=HO2,
                    symptoms="Stock-unit rollover posts a duplicate discrepancy to the local suspense account; "
                             "the shortfall appears at trading-period end",
                    date_reported="2013-09-09"),
}

SAMPLE_LATER_DEFECT = dict(
    defect_id="KEL-D07", type="KEL", affected_branches="214;117", affected_start="2013-02-01",
    affected_end="2013-07-31", versions=HO2,
    symptoms="Reversal of a failed bill-payment recovery leaves a phantom debit in the cash account",
    date_reported="2013-11-15")

# Pairs an independent reviewer judged relevant (used for recall and precision).
GROUND_TRUTH_RELEVANT = {
    ("C014", "KEL-D01"), ("C008", "KEL-D01"), ("C003", "KEL-D05"),
    ("C014", "KEL-D07"), ("C011", "KEL-D07"),
}

COMPLAINTS = [
    dict(complaint_id="HL-0811", branch="042", date="2008-04-14",
         issue="System froze during a stock transfer; SPM queried a duplicated transfer"),
    dict(complaint_id="HL-1302", branch="117", date="2013-02-26",
         issue="Bill-payment reversal left a debit the SPM cannot explain"),
    dict(complaint_id="HL-1305", branch="214", date="2013-05-03",
         issue="Unexplained loss after stock-unit rollover; SPM asked for transaction logs"),
    dict(complaint_id="HL-1306", branch="305", date="2013-05-20",
         issue="Repeat discrepancy at rollover; SPM made good £600 from own funds"),
    dict(complaint_id="HL-1309", branch="233", date="2013-06-24",
         issue="Cash declaration discrepancy after a counter restart"),
    dict(complaint_id="HL-1314", branch="156", date="2013-09-10",
         issue="Trading statement printout unreadable"),
]


class Timeline:
    """Replays dated events and runs the Rule 4 sweep for every day in between."""

    def __init__(self, conn):
        self.conn = conn
        self.swept_to = date(2013, 1, 1)

    def at(self, iso: str, hhmm: str = "09:00") -> datetime:
        when = datetime.strptime(f"{iso} {hhmm}", "%Y-%m-%d %H:%M")
        d = self.swept_to + timedelta(days=1)
        while d <= when.date():
            S.run_escalation_sweep(self.conn, datetime.combine(d, datetime.min.time()).replace(hour=8))
            d += timedelta(days=1)
        self.swept_to = max(self.swept_to, when.date())
        return when


_BUILD_LOCK = threading.RLock()


def build(path: str | Path = db.DEFAULT_DB_PATH) -> Path:
    """Build the demo database in a temporary file, then swap it in atomically.

    Visitors never see a half-built database, and concurrent first visitors on a
    hosted deployment cannot build it at the same time. Durability pragmas are
    off during the build because a failed build is simply rebuilt.
    """
    path = Path(path)
    with _BUILD_LOCK:
        tmp = path.with_name(path.name + ".building")
        tmp.unlink(missing_ok=True)
        conn = db.connect(tmp)
        conn.execute("PRAGMA synchronous = OFF")
        conn.execute("PRAGMA journal_mode = MEMORY")
        db.init_db(conn)
        populate(conn)
        conn.close()
        os.replace(tmp, path)
    return path


def ensure(path: str | Path = db.DEFAULT_DB_PATH) -> Path:
    """Build the demo database only if it does not exist yet."""
    path = Path(path)
    with _BUILD_LOCK:
        if not path.exists():
            build(path)
    return path


def populate(conn) -> None:
    for u in USERS:
        conn.execute("INSERT INTO users (user_id, name, role, is_external, note) VALUES (?, ?, ?, ?, ?)", u)
    db.set_meta(conn, "demo_date", DEMO_DATE.isoformat())
    conn.commit()

    a = {u[0]: S.get_actor(conn, u[0]) for u in USERS}
    tan, shah, okafor, patel = a["u_tan"], a["u_shah"], a["u_okafor"], a["u_patel"]
    lim, wong, morgan = a["u_lim"], a["u_wong"], a["u_morgan"]
    t = Timeline(conn)

    def defect(defect_id, when, hhmm="10:00"):
        S.load_defect(conn, okafor, t.at(when, hhmm), DEFECTS[defect_id],
                      source_file=f"fujitsu_peak_kel_extract_{when}.csv")

    def deliver(case_id, item, ref, start, end, when, availability=R.DELIVERED, notes="", hhmm="11:00"):
        S.record_supplier_delivery(conn, okafor, t.at(when, hhmm), case_id=case_id, item_type=item,
                                   request_ref=ref, period_start=start, period_end=end,
                                   availability=availability, notes=notes)

    def task_for(case_id, type_, item_type=None):
        tasks = [x for x in S.case_tasks(conn, case_id, open_only=True) if x["type"] == type_
                 and (item_type is None or x["item_type"] == item_type)]
        return tasks[-1]["task_id"]

    # --- Defects known before the 2013 cases -------------------------------
    defect("PEAK-P03", "2013-01-14")
    defect("KEL-D02", "2013-02-20")

    # --- C011: CERT-era case, reviewed and closed (caught live by KEL-D07) --
    S.register_case(conn, shah, t.at("2013-04-08"), dict(
        case_id="C011", branch="117", branch_name="Riverside", disputed_start="2013-02-04",
        disputed_end="2013-03-03", horizon_version=HO2, amount=2640.0,
        spm_explanation="The SPM accepted that the account was short but could not explain a debit "
                        "following a bill-payment reversal on 26 Feb 2013."), "pol_case_register.csv")
    deliver("C011", R.ARQ, "ARQ-2013-0122", "2013-02-04", "2013-03-03", "2013-04-12")
    deliver("C011", R.REMOTE_LOGS, "RIL-2013-0122", "2013-02-04", "2013-03-03", "2013-04-12")
    S.record_review(conn, wong, t.at("2013-04-22", "14:00"), "C011", declared_no_involvement=True,
                    decision=R.RELY, reasons="Complete ARQ data for the disputed period reconciles to the "
                    "declared shortfall. No known defect identified at the date of review (not confirmation "
                    "of reliability). SPM given the evidence relied on.")
    S.attempt_reliance(conn, shah, t.at("2013-04-23"), "C011", R.RELIANCE_ACTIONS[0])
    S.close_case(conn, morgan, t.at("2013-08-30"), "C011", "Recovery completed by agreed deductions")

    # --- C001: fully clear case --------------------------------------------
    S.register_case(conn, tan, t.at("2013-09-02"), dict(
        case_id="C001", branch="101", branch_name="Ashby Road", disputed_start="2013-07-01",
        disputed_end="2013-07-28", horizon_version=HO2, amount=1150.0,
        spm_explanation="The SPM believes a cash remittance of £1,150 was mis-keyed on 12 Jul 2013 and "
                        "asks for a full transaction check."), "pol_case_register.csv")
    deliver("C001", R.ARQ, "ARQ-2013-0391", "2013-07-01", "2013-07-28", "2013-09-09")
    deliver("C001", R.REMOTE_LOGS, "RIL-2013-0391", "2013-07-01", "2013-07-28", "2013-09-09")
    S.record_review(conn, wong, t.at("2013-09-16", "15:00"), "C001", declared_no_involvement=True,
                    decision=R.RELY, reasons="Complete ARQ data reconciles to the shortfall; the mis-keyed "
                    "remittance described by the SPM is visible on 12 Jul and accounts for the figure. No known "
                    "defect identified (not confirmation of reliability). The SPM has been given the records.")

    # --- C009: unavailable evidence, exception validly authorised ----------
    S.register_case(conn, shah, t.at("2013-09-16", "16:00"), dict(
        case_id="C009", branch="172", branch_name="Ferry Street", disputed_start="2013-03-04",
        disputed_end="2013-04-14", horizon_version=HO2, amount=5600.0,
        spm_explanation="The SPM disputes the whole shortfall and says counter totals did not match "
                        "printed receipts in early April."), "pol_case_register.csv")
    deliver("C009", R.ARQ, "ARQ-2013-0402", "2013-03-04", "2013-03-31", "2013-09-20")
    deliver("C009", R.REMOTE_LOGS, "RIL-2013-0402", "2013-03-04", "2013-04-14", "2013-09-20")

    # --- C010: unavailable evidence, conflicted authoriser rejected -------
    S.register_case(conn, tan, t.at("2013-09-23"), dict(
        case_id="C010", branch="199", branch_name="Old Quay", disputed_start="2013-02-04",
        disputed_end="2013-03-17", horizon_version=HO2, amount=7250.0,
        spm_explanation="The SPM says the shortfall built up after a counter replacement in February.",
        involved_users=["u_tan", "u_morgan"],
        involvement_notes={"u_tan": "Investigator",
                           "u_morgan": "Approved the original charging decision (Jul 2013)"}),
        "pol_case_register.csv")
    deliver("C010", R.ARQ, "ARQ-2013-0417", "2013-02-04", "2013-03-03", "2013-09-27")
    deliver("C010", R.REMOTE_LOGS, "RIL-2013-0417", "2013-02-04", "2013-03-17", "2013-09-27")

    # --- C003: closed Legacy Horizon case from 2008, migrated to the index -
    S.register_case(conn, morgan, t.at("2013-09-30", "16:00"), dict(
        case_id="C003", branch="042", branch_name="Hollins Cross", disputed_start="2008-03-03",
        disputed_end="2008-04-25", horizon_version="Legacy Horizon", amount=11850.0, status="closed",
        closed_on="2009-06-12", closure_note="Prosecution concluded (legacy file)",
        spm_explanation="The SPM said the shortfall appeared after repeated system freezes during stock "
                        "transfers and that no cash was taken.",
        involved_users=["u_shah"], involvement_notes={"u_shah": "Original investigator (2008)"},
        historical_decision=dict(date="2009-06-12 00:00", decision="Prosecution concluded; recovery order",
                                 reasons="Legacy file: guilty plea to false accounting; recovery order for "
                                         "£11,850. No ARQ request or defect search recorded.")),
        "legacy_case_index_migration.csv")

    S.load_complaints(conn, morgan, t.at("2013-10-01", "09:30"), COMPLAINTS, "pol_helpline_extract_2013-10.csv")
    defect("PEAK-P08", "2013-10-01")

    S.record_supplier_delivery(conn, okafor, t.at("2013-10-03", "10:00"), case_id="C009", item_type=R.ARQ,
                               request_ref="ARQ-2013-0402b", period_start="2013-04-01", period_end="2013-04-14",
                               availability=R.UNAVAILABLE,
                               notes="Supplier confirms archive for 1–14 Apr 2013 was not retained")
    S.close_retrieval_unavailable(conn, okafor, t.at("2013-10-03", "15:00"), task_for("C009", "Evidence retrieval"),
                                  "Requested 20 Sep; chased 26 Sep; supplier confirmed on 3 Oct that the archive "
                                  "for 1–14 Apr 2013 was not retained; escalated to the supplier account manager; "
                                  "no alternative source identified.")
    S.record_supplier_delivery(conn, okafor, t.at("2013-10-10", "10:00"), case_id="C010", item_type=R.ARQ,
                               request_ref="ARQ-2013-0417b", period_start="2013-03-04", period_end="2013-03-17",
                               availability=R.UNAVAILABLE,
                               notes="Supplier confirms the transaction archive for 4–17 Mar 2013 is corrupt")
    S.close_retrieval_unavailable(conn, okafor, t.at("2013-10-10", "15:00"), task_for("C010", "Evidence retrieval"),
                                  "Requested 27 Sep; supplier reported corruption on 10 Oct; second extraction "
                                  "attempt failed; backup media checked; no alternative source identified.")

    # --- KEL-D05 arrives: Rule 5 catches closed 2008 case C003 -------------
    defect("KEL-D05", "2013-10-14")

    # --- C006: overdue routine request (10 / 20 working days) --------------
    S.register_case(conn, tan, t.at("2013-10-14", "11:00"), dict(
        case_id="C006", branch="156", branch_name="Marsh Road", disputed_start="2013-08-19",
        disputed_end="2013-09-29", horizon_version=HO2, amount=6420.0,
        spm_explanation="The SPM reports the trading statement could not be read and disputes the "
                        "September balance."), "pol_case_register.csv")
    deliver("C006", R.REMOTE_LOGS, "RIL-2013-0455", "2013-08-19", "2013-09-29", "2013-10-17")
    S.record_inquiry_outcome(conn, tan, t.at("2013-10-18", "16:00"), task_for("C006", "Defect inquiry"),
                             outcome=S.INQUIRY_NOT_RELEVANT,
                             finding="PEAK-P08 affects printed statement layout only; branch transaction "
                                     "totals checked against the counter log are unaffected.")

    # --- C005: complete evidence; investigator later attempts self-approval -
    S.register_case(conn, shah, t.at("2013-10-21"), dict(
        case_id="C005", branch="088", branch_name="Kirkby Lane", disputed_start="2013-05-06",
        disputed_end="2013-06-02", horizon_version=HO2, amount=2980.0,
        spm_explanation="The SPM accepts a cash shortfall but says part of it was a lottery prize paid "
                        "out without the system recording it."), "pol_case_register.csv")

    # --- C009 exception: proposed, separately authorised, then reviewed ----
    S.propose_exception(conn, lim, t.at("2013-10-21", "14:00"), "C009", item_type=R.ARQ,
                        implications="The £1,900 of the shortfall arising in 1–14 Apr 2013 cannot be tested "
                                     "against audit data.",
                        proposed_action="Limit any recovery to the £3,700 evidenced by complete ARQ data for "
                                        "4–31 Mar; do not pursue the £1,900; disclose the gap to the SPM.",
                        reasons="Retrieval exhausted and documented; the limited action relies only on figures "
                                "that have been tested.", duties_confirmed=True)

    # --- C014: report Section 4.2.6 -----------------------------------------
    S.register_case(conn, tan, t.at("2013-10-22"), dict(
        case_id="C014", branch="214", branch_name="Elmfield", disputed_start="2013-04-01",
        disputed_end="2013-05-12", horizon_version=HO2, amount=4200.0,
        spm_explanation="The SPM disputes the £4,200 shortfall, saying discrepancies appeared after "
                        "stock-unit rollovers in April and May 2013 and that no cash was removed. The SPM "
                        "asked the helpline for transaction logs on 3 May 2013."), "pol_case_register.csv")

    S.authorise_exception(conn, morgan, t.at("2013-10-23", "10:00"), "EX-001", independence_confirmed=True)

    deliver("C014", R.ARQ, "ARQ-2013-0468", "2013-04-01", "2013-04-28", "2013-10-24", hhmm="10:00",
            notes="Supplier extract covers four of the six requested weeks")
    deliver("C014", R.REMOTE_LOGS, "RIL-2013-0468", "2013-04-01", "2013-05-12", "2013-10-24", hhmm="10:05")
    S.attempt_reliance(conn, tan, t.at("2013-10-24", "15:30"), "C014", R.RELIANCE_ACTIONS[0])

    S.record_review(conn, lim, t.at("2013-10-24", "16:00"), "C009", declared_no_involvement=True,
                    decision=R.RELY, reasons="Reliance limited to the £3,700 evidenced for 4–31 Mar under "
                    "exception EX-001. The ARQ gap for 1–14 Apr remains on the file and has been disclosed "
                    "to the SPM; no known defect identified (not confirmation of reliability).")
    deliver("C005", R.ARQ, "ARQ-2013-0462", "2013-05-06", "2013-06-02", "2013-10-25")
    deliver("C005", R.REMOTE_LOGS, "RIL-2013-0462", "2013-05-06", "2013-06-02", "2013-10-25", hhmm="11:05")

    defect("KEL-D01", "2013-10-28")  # reported 9 Sep, months after the dispute; links to C014

    S.record_expert_statement(conn, patel, t.at("2013-10-30", "14:00"), case_id="C014", statement_id="ES-014",
                              author="Dr P. Grant", defects_addressed=["KEL-D02"],
                              summary="States that Horizon operated correctly at branch 214 during the "
                                      "disputed period; considers KEL-D02 only.")
    S.run_expert_check(conn, patel, t.at("2013-11-04", "10:00"), "C014",
                       notes="Statement does not address KEL-D01, which is linked to this case.")

    # --- C007: urgent – legal deadline within five working days ------------
    S.register_case(conn, shah, t.at("2013-11-04", "11:00"), dict(
        case_id="C007", branch="233", branch_name="Wellgate", disputed_start="2013-06-03",
        disputed_end="2013-07-14", horizon_version=HO2, amount=8900.0,
        legal_deadline="2013-11-21", legal_deadline_note="Prosecution disclosure due at Crown Court",
        spm_explanation="The SPM says the counter restarted twice during cash declarations in late June."),
        "pol_case_register.csv")

    S.propose_exception(conn, wong, t.at("2013-11-05", "10:00"), "C010", item_type=R.ARQ,
                        implications="The £2,400 attributed to 4–17 Mar 2013 cannot be tested against audit data.",
                        proposed_action="Limit any recovery to the £4,850 evidenced for 4 Feb – 3 Mar; disclose "
                                        "the gap to the SPM.",
                        reasons="Retrieval exhausted and documented; action limited to tested figures.",
                        duties_confirmed=True)

    S.record_inquiry_outcome(conn, tan, t.at("2013-11-06", "15:00"), task_for("C014", "Defect inquiry"),
                             outcome=S.INQUIRY_RELEVANT, may_undermine=True,
                             finding="Two rollover discrepancies on 29 Apr and 2 May match the KEL-D01 symptom "
                                     "pattern; technical advice from S. Patel supports the comparison.")
    S.acknowledge_escalation(conn, morgan, t.at("2013-11-07", "09:30"), task_for("C014", "Escalation"),
                             "Referred to independent legal reviewer J. Lim for disclosure assessment; "
                             "recovery remains on hold.")
    S.authorise_exception(conn, morgan, t.at("2013-11-07", "11:00"), "EX-002", independence_confirmed=True)

    deliver("C007", R.ARQ, "ARQ-2013-0489", "2013-06-03", "2013-07-14", "2013-11-08")
    deliver("C007", R.REMOTE_LOGS, "RIL-2013-0489", None, None, "2013-11-08", availability=R.UNCONFIRMED,
            notes="Supplier has not confirmed whether remote-access logs were retained", hhmm="11:05")

    # --- C008: Horizon version Unknown -> manual-review queue --------------
    S.register_case(conn, tan, t.at("2013-11-11"), dict(
        case_id="C008", branch="305", branch_name="Northgate", disputed_start="2013-04-15",
        disputed_end="2013-05-26", horizon_version=R.UNKNOWN, amount=3310.0,
        spm_explanation="The SPM reports repeat discrepancies at each rollover and made good £600 "
                        "from personal funds in May."), "pol_case_register.csv")

    S.record_review(conn, lim, t.at("2013-11-11", "14:00"), "C014", declared_no_involvement=True,
                    conflict_note="no role in the investigation, charging or recovery of this case",
                    decision=R.REFER_PROSECUTOR,
                    reasons="KEL-D01 matches the branch, version and disputed period and the investigator's "
                            "comparison supports its relevance. The expert statement omits KEL-D01. This "
                            "material must reach the prosecutor for disclosure assessment. Recovery remains on "
                            "hold while the ARQ request (29 Apr – 12 May) and the expert correction are open.")

    S.record_review(conn, shah, t.at("2013-11-12", "10:00"), "C005", declared_no_involvement=True,
                    decision=R.RELY, reasons="Evidence complete; I recommend recovery proceeds.")
    S.propose_exception(conn, wong, t.at("2013-11-13", "10:00"), "C006", item_type=R.ARQ,
                        implications="ARQ data not yet received for the disputed period.",
                        proposed_action="Proceed on branch-held records.",
                        reasons="Supplier is late and the case is ageing.", duties_confirmed=True)

    deliver("C008", R.ARQ, "ARQ-2013-0497", "2013-04-15", "2013-05-26", "2013-11-14")
    deliver("C008", R.REMOTE_LOGS, "RIL-2013-0497", "2013-04-15", "2013-05-26", "2013-11-14", hhmm="11:05")

    t.at(DEMO_DATE.isoformat(), "08:00")
    conn.commit()


def demo_now(day: date = DEMO_DATE) -> datetime:
    return datetime.combine(day, datetime.now().time()).replace(microsecond=0)


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else db.DEFAULT_DB_PATH
    print(f"Seeded {build(target)}")
