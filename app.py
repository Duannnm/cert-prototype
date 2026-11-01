"""CERT – Case Evidence Review Tracker (IS4234 prototype).

Run locally:  pip install -r requirements.txt && streamlit run app.py
"""
import streamlit as st

import services as S
import ui

st.set_page_config(page_title="CERT – Case Evidence Review Tracker", page_icon="⚖️", layout="wide")

ui.init()
ui.sidebar()
S.run_escalation_sweep(ui.conn(), ui.now())

pages = {
    "Casework": [
        st.Page("pages/case_list.py", title="Case list", icon=":material/folder_open:", default=True),
        st.Page("pages/case_view.py", title="Case view", icon=":material/gavel:", url_path="case"),
        st.Page("pages/defects.py", title="Defect records", icon=":material/bug_report:", url_path="defects"),
    ],
    "Oversight": [
        st.Page("pages/dashboard.py", title="Oversight dashboard", icon=":material/monitoring:",
                url_path="dashboard"),
        st.Page("pages/audit_log.py", title="Audit log & integrity", icon=":material/fact_check:",
                url_path="audit"),
        st.Page("pages/about.py", title="About & limitations", icon=":material/info:", url_path="about"),
    ],
}
st.navigation(pages).run()
