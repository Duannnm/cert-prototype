"""SQLite schema and low-level access for CERT.

Two integrity mechanisms live here:
  * source_records keeps every received record exactly as it arrived (original
    ID, source file, receipt time, SHA-256). A hash proves a record is unchanged
    since receipt, not that it is true.
  * audit_log is append-only (triggers reject UPDATE/DELETE) and hash-chained,
    so the history of a case cannot be rewritten without a reviewable trace.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent / "data" / "cert.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL,
    is_external INTEGER NOT NULL DEFAULT 0, note TEXT);

CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY, branch TEXT, branch_name TEXT,
    disputed_start TEXT, disputed_end TEXT, horizon_version TEXT, amount REAL,
    stage INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'active',
    spm_explanation TEXT,
    involved_users TEXT NOT NULL DEFAULT '[]', involvement_notes TEXT NOT NULL DEFAULT '{}',
    legal_deadline TEXT, legal_deadline_note TEXT,
    registered_by TEXT, registered_on TEXT, closed_on TEXT, closure_note TEXT,
    evidence_version INTEGER NOT NULL DEFAULT 1, source_record_id TEXT);

CREATE TABLE IF NOT EXISTS defects (
    defect_id TEXT PRIMARY KEY, type TEXT, affected_branches TEXT,
    affected_start TEXT, affected_end TEXT, versions TEXT, symptoms TEXT,
    date_reported TEXT, loaded_on TEXT, record_version INTEGER NOT NULL DEFAULT 1,
    source_record_id TEXT);

CREATE TABLE IF NOT EXISTS evidence_items (
    case_id TEXT, item_type TEXT, status TEXT, period_covered TEXT, reason TEXT,
    owner TEXT, since TEXT, updated_on TEXT, PRIMARY KEY (case_id, item_type));

CREATE TABLE IF NOT EXISTS supplier_deliveries (
    delivery_id TEXT PRIMARY KEY, case_id TEXT, item_type TEXT, request_ref TEXT,
    period_start TEXT, period_end TEXT, availability TEXT, received_on TEXT,
    notes TEXT, recorded_by TEXT, source_record_id TEXT);

CREATE TABLE IF NOT EXISTS complaints (
    complaint_id TEXT PRIMARY KEY, branch TEXT, date TEXT, issue TEXT, source_record_id TEXT);

CREATE TABLE IF NOT EXISTS defect_links (
    case_id TEXT, defect_id TEXT, result TEXT, matched_fields TEXT, explanation TEXT,
    inquiry_status TEXT, inquiry_finding TEXT, created_by_rule TEXT,
    created_on TEXT, updated_on TEXT, defect_version INTEGER,
    PRIMARY KEY (case_id, defect_id));

CREATE TABLE IF NOT EXISTS expert_statements (
    statement_id TEXT, case_id TEXT, author TEXT, version INTEGER,
    linked_defects TEXT, summary TEXT, submitted_on TEXT, source_record_id TEXT,
    PRIMARY KEY (statement_id, version));

CREATE TABLE IF NOT EXISTS expert_checks (
    check_id TEXT PRIMARY KEY, statement_id TEXT, statement_version INTEGER, case_id TEXT,
    checker TEXT, checked_on TEXT, relevant_defects TEXT, omissions TEXT,
    correction_status TEXT, notes TEXT);

CREATE TABLE IF NOT EXISTS reviews (
    review_id TEXT PRIMARY KEY, case_id TEXT, reviewer TEXT, conflict_declaration TEXT,
    evidence_version INTEGER, decision TEXT, reasons TEXT,
    exception_flag INTEGER NOT NULL DEFAULT 0, exception_authoriser TEXT, exception_id TEXT,
    recorded_on TEXT, is_historical INTEGER NOT NULL DEFAULT 0);

CREATE TABLE IF NOT EXISTS exceptions (
    exception_id TEXT PRIMARY KEY, case_id TEXT, item_type TEXT, gap TEXT,
    implications TEXT, proposed_action TEXT, reasons TEXT, duties_confirmed INTEGER,
    proposed_by TEXT, proposed_on TEXT, status TEXT, authoriser TEXT, authorised_on TEXT);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY, case_id TEXT, type TEXT, title TEXT, detail TEXT,
    owner TEXT, owner_role TEXT, created TEXT, schedule_due TEXT,
    status TEXT NOT NULL DEFAULT 'Open', required INTEGER NOT NULL DEFAULT 1,
    urgent INTEGER NOT NULL DEFAULT 0, escalate_to TEXT,
    escalation_level TEXT NOT NULL DEFAULT 'None',
    linked_to TEXT, defect_id TEXT, item_type TEXT,
    closed_on TEXT, closed_by TEXT, outcome TEXT, closure_note TEXT);

CREATE TABLE IF NOT EXISTS gate_attempts (
    attempt_id TEXT PRIMARY KEY, case_id TEXT, ts TEXT, user TEXT, role TEXT,
    action TEXT, category TEXT, outcome TEXT, reasons TEXT);

CREATE TABLE IF NOT EXISTS source_records (
    record_id TEXT PRIMARY KEY, source_type TEXT, source_file TEXT, original_id TEXT,
    received_at TEXT, raw_content TEXT, sha256 TEXT);

CREATE TABLE IF NOT EXISTS audit_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, recorded_at TEXT NOT NULL,
    user TEXT, role TEXT, action TEXT NOT NULL, object TEXT, case_id TEXT,
    before TEXT, after TEXT, prev_hash TEXT NOT NULL, entry_hash TEXT NOT NULL);
"""

PROTECTION_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS source_records_no_update BEFORE UPDATE ON source_records
BEGIN SELECT RAISE(ABORT, 'source_records are immutable; add a new version instead'); END;
CREATE TRIGGER IF NOT EXISTS source_records_no_delete BEFORE DELETE ON source_records
BEGIN SELECT RAISE(ABORT, 'source_records are immutable'); END;
"""

GENESIS_HASH = "0" * 64


class CertConnection(sqlite3.Connection):
    """Connection that lets nested service calls share one transaction."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tx_depth = 0


def connect(path: str | Path = DEFAULT_DB_PATH) -> CertConnection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, factory=CertConnection, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.executescript(PROTECTION_TRIGGERS)
    conn.commit()


# --- JSON and hashing helpers -------------------------------------------------

def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def to_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def from_json(text, default=None):
    if text is None or text == "":
        return default
    return json.loads(text)


def sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


# --- IDs and metadata ---------------------------------------------------------

def next_id(conn: sqlite3.Connection, prefix: str, width: int = 3) -> str:
    key = f"seq:{prefix}"
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    n = int(row["value"]) + 1 if row else 1
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, str(n)))
    return f"{prefix}-{n:0{width}d}"


def get_meta(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value) -> None:
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, str(value)))


# --- Source records -----------------------------------------------------------

def add_source_record(conn: sqlite3.Connection, *, source_type: str, source_file: str,
                      original_id: str, received_at: str, payload: dict) -> str:
    """Store a received record verbatim with its SHA-256 fingerprint."""
    raw = canonical_json(payload)
    record_id = next_id(conn, "SR", 4)
    conn.execute(
        "INSERT INTO source_records (record_id, source_type, source_file, original_id, received_at,"
        " raw_content, sha256) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (record_id, source_type, source_file, original_id, received_at, raw, sha256_of(raw)),
    )
    return record_id


def verify_source_records(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM source_records ORDER BY record_id").fetchall()
    results = []
    for r in rows:
        actual = sha256_of(r["raw_content"])
        results.append({
            "record_id": r["record_id"], "source_type": r["source_type"],
            "original_id": r["original_id"], "source_file": r["source_file"],
            "received_at": r["received_at"], "stored_sha256": r["sha256"],
            "recomputed_sha256": actual,
            "result": "Unchanged" if actual == r["sha256"] else "ALTERED",
        })
    return results


# --- Append-only, hash-chained audit log ---------------------------------------

def _entry_hash(prev_hash: str, fields: dict) -> str:
    return sha256_of(prev_hash + canonical_json(fields))


def append_audit(conn: sqlite3.Connection, *, ts: str, user: str, role: str, action: str,
                 obj: str = "", case_id: str | None = None, before=None, after=None) -> int:
    last = conn.execute("SELECT entry_hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
    prev_hash = last["entry_hash"] if last else GENESIS_HASH
    fields = {
        "ts": ts, "recorded_at": utc_now(), "user": user, "role": role, "action": action,
        "object": obj, "case_id": case_id,
        "before": None if before is None else to_json(before),
        "after": None if after is None else to_json(after),
    }
    cur = conn.execute(
        "INSERT INTO audit_log (ts, recorded_at, user, role, action, object, case_id, before, after,"
        " prev_hash, entry_hash) VALUES (:ts, :recorded_at, :user, :role, :action, :object, :case_id,"
        " :before, :after, :prev_hash, :entry_hash)",
        {**fields, "prev_hash": prev_hash, "entry_hash": _entry_hash(prev_hash, fields)},
    )
    return cur.lastrowid


def verify_audit_chain(conn: sqlite3.Connection) -> dict:
    rows = conn.execute("SELECT * FROM audit_log ORDER BY seq").fetchall()
    prev = GENESIS_HASH
    for r in rows:
        fields = {k: r[k] for k in ("ts", "recorded_at", "user", "role", "action", "object",
                                    "case_id", "before", "after")}
        if r["prev_hash"] != prev or r["entry_hash"] != _entry_hash(prev, fields):
            return {"ok": False, "entries": len(rows), "first_broken_seq": r["seq"]}
        prev = r["entry_hash"]
    return {"ok": True, "entries": len(rows), "first_broken_seq": None}
