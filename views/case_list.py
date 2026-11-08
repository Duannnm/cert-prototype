import pandas as pd
import streamlit as st

import rules as R
import services as S
import ui

conn = ui.conn()
ui.header("Case list", f"Demo date {R.fmt_date(ui.today())} · synthetic data")
ui.render_flash()

visible_ids = {c["case_id"] for c in S.visible_cases(conn, ui.actor())}
rows = [r for r in S.case_overview(conn, ui.today()) if r["case_id"] in visible_ids]
active = [r for r in rows if r["status"] == "Active"]
cols = st.columns(5)
cols[0].metric("Active cases", len(active))
cols[1].metric("Closed cases", len(rows) - len(active))
cols[2].metric("Reliance blocked", sum(r["gate"] == R.BLOCKED for r in rows))
cols[3].metric("Reliance clear", sum(r["gate"] == R.CLEAR for r in rows))
cols[4].metric("Cases with escalations", sum(r["escalation_level"] != R.ESC_NONE for r in rows))

f1, f2, f3 = st.columns([1, 1, 2])
status = f1.selectbox("Status", ["All", "Active", "Closed"])
gate = f2.selectbox("Reliance gate", ["All", R.BLOCKED, R.CLEAR, R.CLOSED])
search = f3.text_input("Search case or branch", placeholder="e.g. C014 or Elmfield")
shown = [r for r in rows
         if (status == "All" or r["status"] == status) and (gate == "All" or r["gate"] == gate)
         and (not search or search.lower() in f"{r['case_id']} {r['branch']}".lower())]

df = pd.DataFrame([{
    "Case": r["case_id"], "Branch": r["branch"], "Status": r["status"],
    "Stage": f"{r['stage']} {ui.STAGES[r['stage'] - 1]}", "Gate": r["gate"], "Open gaps": r["open_gaps"],
    "Open inquiries": r["open_inquiries"], "Escalation": r["escalation"], "Disputed": r["amount"],
    "Disputed period": r["period"], "Horizon version": r["version"]} for r in shown])

GATE_STYLE = {R.BLOCKED: "background-color:#fdeaea;color:#8f1d1d;font-weight:700",
              R.CLEAR: "background-color:#e5f4ea;color:#1b5e33;font-weight:700",
              R.CLOSED: "background-color:#eef1f4;color:#46525e;font-weight:700"}


def esc_style(v: str) -> str:
    if v.startswith("Immediate") or v.startswith("20 WD"):
        return "color:#8f1d1d;font-weight:600"
    return "color:#7c4a03;font-weight:600" if v.startswith("10 WD") else ""


st.caption("Select a row to open the case view.")
if df.empty:
    st.info("No cases match these filters.")
else:
    styled = (df.style.map(lambda v: GATE_STYLE.get(v, ""), subset=["Gate"])
              .map(esc_style, subset=["Escalation"])
              .map(lambda v: "color:#7c4a03;font-weight:600" if v else "", subset=["Open gaps"])
              .format({"Disputed": "£{:,.0f}"}))
    event = st.dataframe(styled, hide_index=True, on_select="rerun", selection_mode="single-row",
                         key="case_table", row_height=36, height=36 * (len(df) + 1) + 4)
    if event.selection.rows:
        case_id = df.iloc[event.selection.rows[0]]["Case"]
        del st.session_state["case_table"]
        st.session_state["case_id"] = case_id
        st.switch_page("views/case_view.py", query_params={"case": case_id})

left, right = st.columns(2)
with left:
    st.subheader("Manual-review queue")
    st.caption("Rule 1 pairs with an Unknown field. They are never discarded; a person decides.")
    queue = [t for t in S.case_tasks(conn, open_only=True) if t["type"] == "Manual review" and t["case_id"] in visible_ids]
    ui.table([{"task": t["task_id"], "case": t["case_id"], "defect": t["defect_id"], "title": t["title"],
               "owner": S.user_name(conn, t["owner"])} for t in queue],
             [("task", "Task"), ("case", "Case"), ("defect", "Defect"), ("title", "Why"), ("owner", "Owner")])
with right:
    me = ui.actor()
    st.subheader("Your open tasks")
    st.caption(f"Assigned to {me.name} ({me.role}).")
    mine = [t for t in S.case_tasks(conn, open_only=True) if t["owner"] == me.user_id]
    cases = {c["case_id"]: c for c in S.list_cases(conn)}
    ui.table([{"task": t["task_id"], "case": t["case_id"], "title": t["title"],
               "esc": ui.chip(S.task_escalation(t, cases[t["case_id"]], ui.today()).label,
                              ui.KIND[S.task_escalation(t, cases[t["case_id"]], ui.today()).level])}
              for t in mine],
             [("task", "Task"), ("case", "Case"), ("title", "Task"), ("esc", "Escalation")], raw=("esc",))

st.subheader("Register a new case")
with st.expander("Stage 1 – Register a case and the SPM's explanation", expanded=False):
    if ui.allowed(R.INVESTIGATOR, action="register a case"):
        existing = {c["case_id"] for c in S.list_cases(conn)}
        n = 15
        while f"C{n:03d}" in existing:
            n += 1
        colleagues = [u for u in S.list_users(conn) if u.user_id != ui.actor().user_id]
        with st.form("register"):
            a, b, c = st.columns(3)
            case_id = a.text_input("Case ID", value=f"C{n:03d}")
            branch = b.text_input("Branch code", placeholder="e.g. 214")
            branch_name = c.text_input("Branch name", placeholder="e.g. Elmfield")
            a, b, c, d = st.columns(4)
            start = a.date_input("Disputed period start", value=None, format="DD/MM/YYYY")
            end = b.date_input("Disputed period end", value=None, format="DD/MM/YYYY")
            version = c.selectbox("Horizon version", [*R.HORIZON_VERSIONS, R.UNKNOWN], index=2)
            amount = d.number_input("Disputed amount (£)", min_value=0.0, step=50.0, value=0.0)
            spm = st.text_area("SPM explanation (the SPM's own account; preserved verbatim)")
            a, b = st.columns(2)
            deadline = a.date_input("Next legal deadline (optional)", value=None, format="DD/MM/YYYY")
            deadline_note = b.text_input("Deadline description", placeholder="e.g. Disclosure due at court")
            others = st.multiselect("Others involved in this case (blocked from reviewing or authorising)",
                                    [u.user_id for u in colleagues], format_func=lambda u: S.get_actor(conn, u).label)
            st.caption("Leave a date empty if it is not known: it is stored as Unknown and sends defect matches "
                       "to the manual-review queue.")
            if st.form_submit_button("Register case and run Rule 1", type="primary"):
                out = S.register_case(conn, ui.actor(), ui.now(), dict(
                    case_id=case_id, branch=branch, branch_name=branch_name,
                    disputed_start=start.isoformat() if start else None,
                    disputed_end=end.isoformat() if end else None, horizon_version=version,
                    amount=amount or None, spm_explanation=spm,
                    legal_deadline=deadline.isoformat() if deadline else None,
                    legal_deadline_note=deadline_note or None,
                    involved_users=[ui.actor().user_id, *others]))
                if out.ok:
                    st.session_state["case_id"] = case_id
                ui.flash(out)
