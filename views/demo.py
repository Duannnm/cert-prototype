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
    ("0:00–1:40 · Identify uncertainty", "Investigator · A. Tan", "case?case=C014",
     "Open C014. Show the gate, evidence coverage and next actions. ARQ covers four of six weeks, and the expert statement omits KEL-D01."),
    ("1:40–2:30 · Test the reliance control", "Investigator · A. Tan", "case?case=C014&tab=reliance",
     "In Reliance & exceptions, attempt Issue recovery demand. Show the blocked attempt and recorded reasons."),
    ("2:30–3:35 · Introduce later evidence", "Supplier liaison manager · M. Okafor", "defects",
     "Switch role, load KEL-D07 in the demo tab, then open C014 and closed case C011 from the result. Explain why earlier decisions need reassessment."),
    ("3:35–4:25 · Show oversight", "Any demo role", "dashboard",
     "Highlight evidence gaps, closed cases awaiting reassessment and blocked self-review attempts. Identify who must act and the escalation threshold."),
    ("4:25–5:10 · Check integrity", "Internal audit · H. Ng", "audit",
     "Verify hashes, expand the demo edit, simulate the change, then verify again. Hashes detect change after receipt but cannot prove the original record true."),
    ("5:10–6:10 · Show test evidence", "Any demo role", "tests",
     "Show the saved evaluation date, sample sizes, nine scenarios and precision. Leave twenty seconds for the limitation and handover."),
]
for title, role, url, action in steps:
    st.subheader(title)
    st.caption("Acting as: " + role)
    st.write(action)
    st.link_button("Open this step", url)
st.caption("Navigation opens the target page without changing your role or loading evidence. "
           "The sidebar role switcher simulates identity. Reset discards demo edits for every visitor.")
