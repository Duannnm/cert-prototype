import streamlit as st

import assurance
import rules as R
import services as S
import ui

ui.header("Clearance verification", "Demonstration of a downstream recovery or legal system")
ui.require_page("clearance")
st.info("POL staff remain CERT's operational users. This screen simulates another system requiring "
        "a current clearance before acting. It sends no demand and has no connection to a real recovery system.")
st.caption("Presenter: C014 refuses clearance. C001 demonstrates valid clearance. A made-up reference, "
           "different action, new review or changed evidence prevents verification.")
cases = [c["case_id"] for c in S.visible_cases(ui.conn(), ui.actor())]
if not cases:
    st.info("No cases are available in your scope.")
    st.stop()
case_id = st.selectbox("Case to verify", cases, index=cases.index("C014") if "C014" in cases else 0)
action = st.selectbox("Requested downstream action", R.RELIANCE_ACTIONS)
ui.gate_banner(S.case_gate(ui.conn(), case_id))
if st.button("Request clearance from CERT", type="primary"):
    result = assurance.issue_clearance(ui.conn(), ui.actor(), ui.now(), case_id, action)
    st.session_state["clearance_issue"] = {"ok": result.ok, "message": result.message,
                                          "problems": result.problems, "data": result.data}
    if result.ok:
        st.session_state["clearance_reference"] = result.data["reference"]
issue = st.session_state.get("clearance_issue")
if issue:
    (st.success if issue["ok"] else st.error)(issue["message"])
    for problem in issue["problems"]:
        st.write(problem)
    if issue["ok"]:
        st.json(issue["data"])
st.subheader("Simulated downstream check")
st.text_input("Clearance reference", key="clearance_reference",
              help="A valid reference is checked against its issued case, action, evidence version and review.")
if st.button("Verify before proceeding"):
    result = assurance.verify_clearance(ui.conn(), ui.actor(), ui.now(), case_id, action,
                                        st.session_state["clearance_reference"])
    (st.success if result.ok else st.error)(result.message)
    for problem in result.problems:
        st.write(problem)
    st.caption("Verification is recorded in the audit log. No actual recovery or legal action was performed.")
st.warning("Production requires mandatory integration in every relevant downstream system, authenticated "
           "access and verification within the action transaction. An optional check can still be bypassed. "
           "A reference is a live lookup identifier, not a signed certificate or evidence of a genuine loss.")
