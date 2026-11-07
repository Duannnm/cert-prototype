import streamlit as st

import assurance
import rules as R
import ui

ui.header("Oversight export", "Evidence for an authorised independent overseer")
st.write("An authorised POL audit or legal-lead user prepares a snapshot for independent scrutiny. "
         "The recipient can trace case decisions, exceptions, follow-up and clearance checks against the audit history.")
st.info("This demonstration downloads a package locally. It does not submit records to a regulator "
        "or grant the recipient any statutory powers.")
if not ui.allowed(R.AUDIT, R.LEGAL_LEAD, action="prepare the oversight package"):
    st.stop()
if st.button("Prepare oversight package", type="primary"):
    result = assurance.oversight_export(ui.conn(), ui.actor(), ui.now())
    if result.ok:
        st.session_state["oversight_package"] = result.data
package = st.session_state.get("oversight_package")
if package:
    manifest = package["manifest"]
    st.success(f"Snapshot ready: {manifest['case_count']} registered cases")
    st.caption("Snapshot prepared " + manifest["exported_at_utc"] + ". Prepare again after further demo actions.")
    st.download_button("Download oversight evidence ZIP", package["bytes"],
                       file_name="CERT_oversight_evidence.zip", mime="application/zip")
    with st.expander("Package manifest and SHA-256 fingerprints"):
        st.json(manifest)
st.subheader("What the overseer checks")
st.write("Review unresolved gaps, late reassessments, exceptions, conflicts and rejected clearance checks. "
         "Trace each item to its case and original decision using the JSON records and audit log.")
st.write("Reconcile registered cases against separately obtained recovery and legal case registers. "
         "A clean export cannot establish that POL registered every relevant case.")
st.caption("The ZIP contains case snapshots, tasks, reviews, exceptions, gate attempts, defect links, "
           "the audit log, source fingerprint checks and integrity results. JSON preserves original field values.")
st.warning("Production requires protected evidence delivery and retention, independent access and appropriate "
           "authority to demand records and investigate bypasses. A manifest stored beside its files is not "
           "independent proof of authenticity. The role switcher only simulates access controls.")
