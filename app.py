"""CERT – Case Evidence Review Tracker (IS4234 prototype).

Run locally:  pip install -r requirements.txt && streamlit run app.py
"""
import streamlit as st

from app_bootstrap import prepare_app_modules

prepare_app_modules()

import services as S
import ui
import access

st.set_page_config(page_title="CERT – Case Evidence Review Tracker", page_icon="⚖️", layout="wide")

ui.init()
ui.sidebar()
S.run_escalation_sweep(ui.conn(), ui.now())

definitions = {
    "Casework": [("case_list", "Case list", "folder_open", ""),
                 ("case_view", "Case view", "gavel", "case"),
                 ("defects", "Defect records", "bug_report", "defects"),
                 ("clearance", "Clearance verification", "verified", "clearance")],
    "Oversight": [("dashboard", "Oversight dashboard", "monitoring", "dashboard"),
                  ("oversight_export", "Oversight export", "archive", "oversight-export"),
                  ("audit_log", "Audit log & integrity", "fact_check", "audit")],
    "Demo & guidance": [("demo", "Demo walkthrough", "slideshow", "demo"),
                        ("test_results", "Test results", "checklist", "tests"),
                        ("about", "About & limitations", "info", "about")],
}
pages = {}
for group, entries in definitions.items():
    permitted = [st.Page(f"views/{name}.py", title=title, icon=f":material/{icon}:",
                         default=name == "case_list", url_path=url or None)
                 for name, title, icon, url in entries if access.page_allowed(ui.actor(), name)]
    if permitted:
        pages[group] = permitted
st.navigation(pages).run()
