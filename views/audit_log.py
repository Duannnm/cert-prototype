import pandas as pd
import streamlit as st

import db
import services as S
import ui

conn = ui.conn()
ui.require_page("audit_log")
ui.header("Audit log & integrity", "Append-only, hash-chained log · SHA-256 source-record fingerprints")
ui.render_flash()

st.subheader("Audit log")
st.caption("Every decision, override, escalation and administrative change. Database triggers reject edits "
           "and deletions; each entry's hash includes the previous entry's hash.")
entries = S.audit_entries(conn)
a, b, c = st.columns([1, 1, 2])
cases = ["All"] + sorted({e["case_id"] for e in entries if e["case_id"]})
case = a.selectbox("Case", cases)
users = ["All"] + sorted({e["user"] for e in entries})
user = b.selectbox("User", users)
text = c.text_input("Action or object contains", placeholder="e.g. Blocked, Rule 5, KEL-D01")
shown = [e for e in entries
         if (case == "All" or e["case_id"] == case) and (user == "All" or e["user"] == user)
         and (not text or text.lower() in f"{e['action']} {e['object']}".lower())]
st.dataframe(pd.DataFrame([{
    "#": e["seq"], "Demo time": e["ts"], "User": e["user"], "Role": e["role"], "Action": e["action"],
    "Object": e["object"], "Case": e["case_id"] or "", "Before": e["before"] or "", "After": e["after"] or "",
    "Recorded (system UTC)": e["recorded_at"], "Entry hash": e["entry_hash"][:16] + "…"} for e in reversed(shown)]),
    hide_index=True, height=420)
st.caption(f"{len(shown)} of {len(entries)} entries. Demo time follows the demo clock; the system time is "
           "when the entry was actually written.")

st.subheader("Integrity checks")
st.markdown("<div class='muted'>A hash proves a record is unchanged since it was received. "
            "<b>It does not prove the record is true.</b></div>", unsafe_allow_html=True)
left, right = st.columns(2)
with left:
    if st.button("Verify hashes", type="primary", icon=":material/verified:"):
        st.session_state["hash_results"] = db.verify_source_records(conn)
    results = st.session_state.get("hash_results")
    if results:
        altered = [r for r in results if r["result"] == "ALTERED"]
        if altered:
            st.error(f"{len(altered)} of {len(results)} source records ALTERED since receipt: "
                     + ", ".join(f"{r['record_id']} ({r['original_id']})" for r in altered))
        else:
            st.success(f"All {len(results)} source records unchanged since receipt.")
        df = pd.DataFrame([{"Record": r["record_id"], "Result": r["result"], "Original ID": r["original_id"],
                            "Source": r["source_type"], "Source file": r["source_file"],
                            "Received": r["received_at"], "Stored SHA-256": r["stored_sha256"][:20] + "…",
                            "Recomputed": r["recomputed_sha256"][:20] + "…"} for r in results])
        st.dataframe(df.style.map(lambda v: "background-color:#fdeaea;color:#8f1d1d;font-weight:700"
                                  if v == "ALTERED" else "color:#1b5e33", subset=["Result"]),
                     hide_index=True, height=300)
with right:
    if st.button("Verify audit-log chain", icon=":material/link:"):
        st.session_state["chain"] = db.verify_audit_chain(conn)
    chain = st.session_state.get("chain")
    if chain:
        if chain["ok"]:
            st.success(f"Chain intact across {chain['entries']} entries.")
        else:
            st.error(f"Chain broken at entry {chain['first_broken_seq']}.")
    with st.expander("Demo only: simulate an out-of-band edit"):
        st.caption("Plays the part of a database administrator who bypasses CERT and edits a stored supplier "
                   "record directly, e.g. narrowing KEL-D01's affected period so it no longer matches C014. "
                   "Verify hashes then reports the record as ALTERED. Reset demo data restores it.")
        records = [r for r in db.verify_source_records(conn) if r["source_type"].startswith("PEAK/KEL")]
        rid = st.selectbox("Source record", [r["record_id"] for r in records],
                           index=next((i for i, r in enumerate(records) if r["original_id"] == "KEL-D01"), 0),
                           format_func=lambda x: f"{x} – {next(r['original_id'] for r in records if r['record_id'] == x)}")
        if st.button("Edit affected_end to 2013-04-15 outside CERT", disabled=not ui.can("simulate_tampering")):
            out = S.simulate_tampering(conn, ui.actor(), ui.now(), rid, "affected_end", "2013-04-15")
            st.session_state.pop("hash_results", None)
            ui.flash(out)
