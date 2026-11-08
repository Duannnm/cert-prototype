import streamlit as st

import services as S
import ui

ui.header("Demo walkthrough", "A 6 minute 30 second route through CERT")
st.write("Follow fictional C014: a £4,200 disputed shortfall over six weeks. "
         "Each step connects an evidence weakness to an accountable control.")
loaded = S.get_defect(ui.conn(), "KEL-D07") is not None
st.info("KEL-D07 is already loaded. Reset demo data in the sidebar before rehearsing the full sequence."
        if loaded else "KEL-D07 has not been loaded. The later-evidence scenario is ready.")
steps = [
    ("0:00–1:00 · Identify uncertainty", "Investigator · A. Tan", "case?case=C014",
     "Open C014. Show the gate, evidence coverage and next actions. ARQ covers four of six weeks, and the expert statement omits KEL-D01."),
    ("1:00–2:20 · Verify before downstream action", "Investigator · A. Tan", "clearance",
     "Request clearance for C014: refused. Select C001, request clearance and verify it: the simulated action may proceed. Change the requested action and verify the same reference again: refused. Explain that production systems must require this check."),
    ("2:20–3:25 · Introduce later evidence", "Supplier liaison manager · M. Okafor", "defects",
     "Switch role, load KEL-D07 in the demo tab, then open C014 and closed case C011 from the result. Explain why earlier decisions need reassessment."),
    ("3:25–4:05 · Show oversight", "Internal audit · H. Ng", "dashboard",
     "Highlight evidence gaps, closed cases awaiting reassessment and blocked self-review attempts. Identify who must act and the escalation threshold."),
    ("4:05–5:05 · Prepare independent scrutiny", "Internal audit · H. Ng", "oversight-export",
     "Prepare the oversight package and point to its manifest. It carries decisions, exceptions, clearance attempts and audit evidence for independent inspection. Download it if needed. No regulator receives it automatically. Explain that separate registers are needed to find omitted cases."),
    ("5:05–6:10 · Show test evidence", "Any demo role", "tests",
     "Show the saved evaluation date, sample sizes, nine core scenarios and supporting assurance tests. Close: POL operates CERT, while mandatory integration and authorised independent scrutiny address bypass incentives. Leave twenty seconds for handover."),
]
for title, role, url, action in steps:
    st.subheader(title)
    st.caption("Acting as: " + role)
    st.write(action)
    st.link_button("Open this step", url)
with st.expander("Who completes reassessment? (Q&A)"):
    st.write("After loading KEL-D07, open C014 or C011 and read the assigned reviewer in Tasks & escalation. "
             "Switch to Independent legal reviewer and select that named user. Only that uninvolved reviewer, "
             "who must differ from the original decision-maker, can complete the reassessment. "
             "A legal lead or Committee member can assign another eligible reviewer. A referral can preserve "
             "unresolved concerns; concluding no referral is needed requires the other required checks to be resolved.")
    st.write("For external scrutiny, switch to External independent overseer, P. Evans. Show that the "
             "dashboard and audit history remain visible, while upload, clearance and case-edit controls are unavailable.")
st.caption("Navigation opens the target page without changing your role or loading evidence. "
           "The sidebar role switcher simulates identity. Reset discards demo edits for every visitor.")
with st.expander("Optional Q&A: stale clearance and integrity"):
    st.write("To show evidence invalidation, first issue a clearance for C001, then load a defect whose scope "
             "actually affects C001. Verification of the earlier reference will fail. KEL-D07 affects C014 "
             "and C011, so it does not invalidate C001's clearance. Avoid improvising this data-entry step "
             "in the timed demo. Automated tests cover this transition.")
    st.link_button("Open integrity checks", "audit")
