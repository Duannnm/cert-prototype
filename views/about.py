import streamlit as st

import rules as R
import ui
import access

ui.header("About & limitations", "IS4234 group project · technology demonstrator")

st.markdown("""
### Purpose
CERT addresses the absence of an accountable link between supplier-held technical evidence and decisions about
individual subpostmasters (root causes RC2, RC3 and RC5). It brings case data and technical records together,
shows which evidence is missing, flags potentially relevant defects, assigns follow-up and records reasoned
decisions. It **blocks reliance on disputed figures** (a recovery demand, or passing figures on as reliable)
until required inquiries are complete and an independent reviewer has recorded a reasoned decision.

**CERT does not decide causation, guilt or disclosure.** A defect link is a reason to inquire, not proof. A
non-match is reported as *no known defect identified*, never as confirmation that Horizon was reliable, because
records may be incomplete and faults unknown.
""")

st.markdown("### Users and decisions supported")
ui.table([
    {"u": R.INVESTIGATOR, "d": "What evidence is still needed; which defects require inquiry"},
    {"u": R.SUPPLIER_LIAISON, "d": "Whether requested supplier data was delivered and covers the disputed period"},
    {"u": R.TECH_REVIEWER, "d": "Whether an expert statement addresses the linked PEAKs/KELs"},
    {"u": R.LEGAL_REVIEWER, "d": "Whether material must be disclosed, whether reliance may proceed, whether "
                                 "earlier decisions need referral"},
    {"u": R.LEGAL_LEAD, "d": "How to resolve overdue work and escalated concerns; authorising exceptions only "
                             "when uninvolved"},
    {"u": R.AUDIT, "d": "Whether controls are operating; where corrective action is required"},
    {"u": R.COMMITTEE, "d": "Overdue or conflicted escalations requiring Committee action"},
    {"u": R.OVERSEER, "d": "Read-only scrutiny of the demo's registered cases, controls and audit evidence"},
], [("u", "User"), ("d", "Decision supported")])

st.subheader("Role permissions")
st.caption("The same policy controls navigation and service permissions. Investigators are POL staff or "
           "act on POL's behalf. They see assigned/involved cases; other roles have all registered synthetic "
           "cases in this demonstration. A legal reviewer assesses cases; an external overseer scrutinises the process.")
ui.table([{"role": role, "actions": ", ".join(action.replace("_", " ") for action, roles in access.PERMISSIONS.items()
                                              if role in roles)} for role in R.ROLES],
         [("role", "Role"), ("actions", "Permitted actions")])

st.markdown("""
### Workflow and rules
1 **Register** the case and the SPM's explanation → 2 **Link** defects → 3 **Check coverage** → 4 **Investigate**
flags, alternatives and expert completeness → 5 **Review** independently → 6 **Escalate** at any stage →
7 **Reassess** on new information. Missing evidence returns a case to Stage 4.

| Rule | What it does |
|---|---|
| 1 Defect linking | Flags a potential link only when branch scope, the defect's *affected* period and Horizon version all match. Any Unknown field goes to the manual-review queue. Every result shows which fields matched or why not. |
| 2 Evidence coverage | ARQ audit data for the full disputed period, remote-intervention logs, defect-search result, SPM explanation and any expert statement relied on: each Complete, Gap or Unknown with scope and reason. Partial coverage is a Gap and assigns retrieval to the supplier liaison. The technical reviewer checks expert statements against linked PEAKs/KELs. |
| 3 Reliance gate | Blocks reliance unless there is no open required inquiry, the expert check is complete and a current independent review by an uninvolved, declared reviewer permits it. Unavailable evidence needs an exception with reasons and separate authorisation; it never bypasses an open inquiry and the gap stays visible. |
| 4 Escalation | Material that may undermine an active case, or a legal deadline within 5 working days, escalates immediately to the legal lead. Routine delay escalates to the legal lead at 10 and the Audit & Risk Committee at 20 working days. **Proposed service standards, not statutory periods.** |
| 5 Reassessment | A new or updated defect record re-runs Rule 1 against all cases, open and closed, regardless of date, and creates reassessment tasks linked to the original decision, which is preserved. |

### Design choices
* **Transparent rules, not machine learning.** Reviewers can see exactly why a link was flagged, and no
  validated training dataset exists.
* **Human-in-the-loop.** The gate never approves anything itself; it only stops reliance until a qualified,
  independent person records a reasoned decision. Labelling non-matches carefully and sampling them in audit
  guards against automation bias.
* **Lineage and auditability.** Each source record keeps its original ID, source file, receipt time and SHA-256
  hash; the audit log is append-only and hash-chained. A hash supports change detection, not proof that a
  record is true.

### What this demonstrator does not do (known limitations)
* All data is synthetic and modelled on records described in the case; no real person, branch or record is used.
* The sidebar role switcher stands in for logins. Production use needs real identity and role-based access
  controls, data minimisation, encryption, retention rules, tested recovery and independent security testing.
* Supplier records are loaded by file upload; direct supplier integration is a later phase.
* The demo clock is user-controlled for demonstration; production needs a trusted time source.
* The shared demo database is reset on request and may be reset by other visitors.
* CERT can expose missing evidence but cannot reconstruct evidence that was never retained, and cannot create
  a willingness to act on what it reveals.
* Thresholds and the 10-working-day supplier evidence schedule are proposals to be validated in a pilot.
* Test results come from synthetic cases written by the team; they cannot establish real-world accuracy.
""")
