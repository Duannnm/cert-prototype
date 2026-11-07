import streamlit as st

import rules as R
import services as S
import ui

conn = ui.conn()
today = ui.today()
ui.header("Oversight dashboard", f"Key risk indicators (Table 4.4) at {R.fmt_date(today)} · synthetic records")
ui.render_flash()

with st.expander("Who acts on these indicators?", expanded=True):
    st.write("**Evidence gaps:** the supplier liaison retrieves missing records and documents availability. "
             "The legal lead resolves overdue requests and the Committee challenges persistent delay.")
    st.write("**Closed cases awaiting reassessment:** the assigned independent reviewer assesses new evidence "
             "against the earlier decision. The Committee follows up overdue reassessments.")
    st.write("**Blocked self-review attempts:** internal audit investigates the attempted conflict and "
             "checks that an uninvolved reviewer has the evidence and authority to act.")
    st.caption("Routine delay: legal lead at 10 working days, Committee at 20. "
               "Urgent concerns escalate immediately. These are proposed service standards, not statutory periods.")
    st.page_link("views/test_results.py", label="See saved control-test results", icon=":material/checklist:")

overview = S.case_overview(conn, today)
escalations = S.open_escalations(conn, today)
open_required = sum(t["required"] for t in S.case_tasks(conn, open_only=True))
cols = st.columns(5)
cols[0].metric("Active cases", sum(r["status"] == "Active" for r in overview))
cols[1].metric("Reliance blocked", sum(r["gate"] == R.BLOCKED for r in overview))
cols[2].metric("Reliance clear", sum(r["gate"] == R.CLEAR for r in overview))
cols[3].metric("Open required inquiries", open_required)
cols[4].metric("Immediate escalations", sum(e["level"] == R.ESC_IMMEDIATE for e in escalations))

st.subheader("Key risk indicators")
kris = S.dashboard_kris(conn, today)
ui.table([{"kri": k["kri"], "rag": ui.chip(k["rag"]), "count": f"<b>{k['count']}</b>", "age": k["age"],
           "threshold": k["threshold"], "to": k["escalates_to"], "detail": ui.esc(k["detail"]) or "—"} for k in kris],
         [("kri", "Key risk indicator"), ("rag", "Status"), ("count", "Count"), ("age", "Age / note"),
          ("threshold", "Threshold"), ("to", "Escalates to"), ("detail", "Detail")],
         raw=("rag", "count", "detail"), nowrap=("rag", "count"))
st.markdown("<div class='muted'><b>Counts are interpreted alongside sampled decision quality, not as proof of "
            "compliance.</b> Thresholds are proposed monitoring rules and service standards to be validated in a "
            "pilot, not statutory periods. Serious concerns escalate immediately; the quarterly Committee summary "
            "supplements, and never delays, urgent action.</div>", unsafe_allow_html=True)

st.subheader("Current escalations")
st.caption("Rule 4 on the demo clock. Move the demo date in the sidebar to watch routine items reach 10 and 20 "
           "working days.")
ui.table([{"level": ui.chip(e["escalation"], ui.KIND[e["level"]]), "case": e["case_id"], "task": e["task_id"],
           "type": e["type"], "title": e["title"], "owner": e["owner"], "age": f"{e['age_wd']} WD",
           "reason": e["reason"]} for e in escalations],
         [("level", "Escalation"), ("case", "Case"), ("task", "Task"), ("type", "Type"), ("title", "Item"),
          ("owner", "Owner"), ("age", "Age"), ("reason", "Why")], raw=("level",), nowrap=("level", "case", "task", "age"))

st.subheader("Control operation: reliance gate and independence")
st.caption("Evidence that the controls operate, for internal audit to sample against source records.")
attempts = S.gate_attempts(conn)
labels = {"reliance": "Reliance actions", "self_review": "Self-review attempts", "review": "Other review attempts",
          "clearance_issue": "Clearance issuance refusals", "clearance_verification": "Downstream clearance checks",
          "exception_proposal": "Exception proposals", "exception_authorisation": "Exception authorisations"}
summary = []
for cat, label in labels.items():
    rows = [a for a in attempts if a["category"] == cat]
    if rows:
        summary.append({"cat": label, "n": len(rows), "blocked": sum(a["outcome"] == "Blocked" for a in rows),
                        "permitted": sum(a["outcome"] == "Permitted" for a in rows)})
ui.table(summary, [("cat", "Control point"), ("n", "Attempts"), ("blocked", "Blocked"), ("permitted", "Permitted")])
blocked = [a for a in attempts if a["outcome"] == "Blocked"]
with st.expander(f"Blocked attempts ({len(blocked)})"):
    ui.table([{"id": a["attempt_id"], "case": a["case_id"], "on": ui.short_ts(a["ts"]),
               "who": f"{S.user_name(conn, a['user'])} ({a['role']})", "action": a["action"],
               "why": "; ".join(x.lstrip("• ") for x in a["reasons"])} for a in blocked],
             [("id", "Attempt"), ("case", "Case"), ("on", "Date"), ("who", "By"), ("action", "Action"),
              ("why", "Reasons recorded")], nowrap=("id", "case", "on"))
