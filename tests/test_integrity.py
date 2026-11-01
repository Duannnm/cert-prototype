"""Supporting controls: protected logs, source-record hashing, wording rules and metrics."""
import re
import sqlite3

import pytest

import db
import evaluation
import rules as R
import services as S
from conftest import NOW


def test_audit_log_is_append_only_and_chained(conn):
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE audit_log SET action = 'edited' WHERE seq = 1")
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM audit_log WHERE seq = 1")
    assert db.verify_audit_chain(conn)["ok"]


def test_source_record_hash_detects_out_of_band_change(conn):
    assert all(r["result"] == "Unchanged" for r in db.verify_source_records(conn))
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE source_records SET raw_content = '{}' WHERE record_id = 'SR-0001'")
    target = conn.execute("SELECT record_id FROM source_records WHERE original_id = 'KEL-D01'").fetchone()[0]
    S.simulate_tampering(conn, S.get_actor(conn, "u_ng"), NOW, target, "affected_end", "2013-04-15")
    altered = [r["record_id"] for r in db.verify_source_records(conn) if r["result"] == "ALTERED"]
    assert altered == [target]


def test_wording_never_claims_cause_or_reliability(conn):
    for case in S.list_cases(conn):
        for link in S.case_links(conn, case["case_id"]):
            text = link["explanation"].lower()
            assert not re.search(r"\bcaused?\b", text)
            if link["result"] == R.NO_MATCH:
                assert "reliable" not in text


def test_metrics_meet_design_targets(tmp_path):
    m = evaluation.compute_metrics(tmp_path)
    assert m["recall"]["value"] == 1.0
    assert m["gate_enforcement"]["value"] == 1.0
    assert m["permitted_allowed"]["value"] == 1.0
