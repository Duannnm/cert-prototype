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
actor = ui.actor()
case = S.get_case(ui.conn(), case_id)
gate = S.case_gate(ui.conn(), case_id)
review = S.latest_review(ui.conn(), case_id)
st.subheader("1. Request a clearance reference")
if gate.state == R.CLEAR:
    st.info("Case eligible for a clearance request. This does not verify the reference entered below.")
else:
    ui.gate_banner(gate)
st.caption("Requesting clearance creates a new reference and fills the field below. "
           "To check an edited reference, use Verify before proceeding instead.")
if st.button("Request clearance from CERT", type="primary"):
    result = assurance.issue_clearance(ui.conn(), actor, ui.now(), case_id, action)
    st.session_state.pop("clearance_verification", None)
    st.session_state["clearance_issue"] = {"context": (case_id, action, actor.user_id),
                                          "ok": result.ok, "message": result.message,
                                          "problems": result.problems, "data": result.data}
    if result.ok:
        st.session_state["clearance_reference"] = result.data["reference"]
issue = st.session_state.get("clearance_issue")
if issue and issue.get("context") == (case_id, action, actor.user_id):
    # Issuance is not the downstream decision. Never display it as a green approval.
    if issue["ok"]:
        st.write("Reference created. Issuing a reference does not approve the downstream action.")
    else:
        st.error(issue["message"])
    for problem in issue["problems"]:
        st.write(problem)
    if issue["ok"]:
        with st.expander("Issued reference details (not a verification result)"):
            st.json(issue["data"])
st.subheader("2. Simulated downstream check")
reference = st.text_input("Clearance reference", key="clearance_reference",
              help="A valid reference is checked against its issued case, action, evidence version and review.")
# A displayed result applies only to these inputs and this live case state.
issued_record = ui.conn().execute(
    "SELECT seq, entry_hash FROM audit_log WHERE action = 'Clearance issued' AND object = ?",
    (reference.strip(),)).fetchone()
context = (case_id, action, reference.strip(), actor.user_id, actor.role,
           case["evidence_version"], review["review_id"] if review else None,
           gate.state, tuple(gate.reasons), tuple(issued_record) if issued_record else None)
verification = st.session_state.get("clearance_verification")
if verification and verification["context"] != context:
    st.session_state.pop("clearance_verification", None)
    verification = None
if st.button("Verify before proceeding"):
    result = assurance.verify_clearance(ui.conn(), actor, ui.now(), case_id, action, reference)
    verification = {"context": context, "ok": result.ok, "message": result.message,
                    "problems": result.problems}
    st.session_state["clearance_verification"] = verification
if verification:
    (st.success if verification["ok"] else st.error)(verification["message"])
    st.caption(f"Checked reference: {reference.strip() or '(blank)'} · Case: {case_id} · Action: {action}")
    for problem in verification["problems"]:
        st.write(problem)
    st.caption("Verification is recorded in the audit log. No actual recovery or legal action was performed.")
else:
    st.info("NOT VERIFIED: click Verify before proceeding to check the current case, action and reference.")
st.warning("Production requires mandatory integration in every relevant downstream system, authenticated "
           "access and verification within the action transaction. An optional check can still be bypassed. "
           "A reference is a live lookup identifier, not a signed certificate or evidence of a genuine loss.")
