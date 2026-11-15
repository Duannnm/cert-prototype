"""Responsibilities, rationale and actual page access for each simulated role."""
import streamlit as st

import access
import rules as R
import services as S
import ui

ui.require_page("roles")
ui.header("Roles", "Responsibilities, separation of duties and access to CERT")
st.write("POL personnel and authorised specialists operate CERT. Internal audit tests its controls, "
         "the Committee handles escalations, and the external overseer scrutinises records without "
         "making operational decisions.")

pages = [("case_list", "Case list"), ("case_view", "Case view"),
         ("defects", "Defect records"), ("clearance", "Clearance verification"),
         ("dashboard", "Oversight dashboard"), ("oversight_export", "Oversight export"),
         ("audit_log", "Audit log & integrity"), ("roles", "Roles"),
         ("test_results", "Test results"), ("about", "About & limitations")]
guide = [
    (R.INVESTIGATOR, "Register cases, record complaints and investigate potential defect links.",
     "Connect the SPM’s account and case evidence to a named inquiry owner.",
     "Assigned/involved cases only. May request/verify clearance and attempt reliance; cannot record an independent legal review."),
    (R.SUPPLIER_LIAISON, "Load defect records, record deliveries and document evidence availability.",
     "Make supplier evidence gaps and retrieval responsibility visible.",
     "May record supplier deliveries and unavailable retrieval outcomes; cannot approve reliance or legal reviews."),
    (R.TECH_REVIEWER, "Investigate technical links, record expert statements and check their completeness.",
     "Bring technical knowledge and omissions into the evidence review.",
     "May load defects and record inquiry outcomes; cannot issue clearance or make the legal review decision."),
    (R.LEGAL_REVIEWER, "Record independent reviews, propose exceptions and complete assigned reassessments.",
     "Separate investigation from reasoned legal assessment and prevent self-review.",
     "No prior involvement; reassessment also excludes the original reviewer. Exception authorisation requires an eligible uninvolved external reviewer; proposers cannot self-authorise."),
    (R.LEGAL_LEAD, "Own the controls, resolve escalations, manage eligible assignments and track referrals.",
     "Give unresolved concerns a control owner with authority to follow through.",
     "May request/verify clearance, prepare exports and authorise exceptions when uninvolved. Cannot replace the independent legal review."),
    (R.AUDIT, "Inspect decisions and control records; prepare oversight exports and run integrity checks.",
     "Test whether controls operate instead of relying on outcome counts.",
     "Cannot edit operational casework, issue clearance or make legal decisions. Includes the demonstration-only tampering exercise."),
    (R.COMMITTEE, "Respond to Committee escalations, manage eligible reassessment assignments and follow-up.",
     "Challenge persistent delay, conflicts and unresolved control failures.",
     "Can acknowledge escalations and manage specified follow-up; cannot issue clearance, record case reviews or prepare exports."),
    (R.OVERSEER, "Independently inspect registered cases, indicators and audit evidence.",
     "Provide scrutiny outside operational management and make bypass concerns reviewable.",
     "Read-only access; no case changes, defect uploads, clearance issuance, reviews, export preparation or demo reset."),
]
rows = []
for role, responsibility, why, limits in guide:
    actor = S.Actor("role-guide", "Role guide", role)
    rows.append({"role": role, "responsibility": responsibility, "why": why,
                 "pages": "; ".join(title for page, title in pages if access.page_allowed(actor, page)),
                 "limits": limits})
ui.table(rows, [("role", "Role"), ("responsibility", "Responsibilities"),
                ("why", "Why this role is needed"), ("pages", "Accessible pages"),
                ("limits", "Actions and boundaries")])
st.caption("Accessible pages are calculated from CERT’s permission policy. Opening a case page does not "
           "grant every action on it; role, case scope, task assignment and conflict checks still apply.")
st.info("The sidebar role switcher simulates identity; it is not authentication. Investigators are POL staff "
        "or act on POL’s behalf. Other roles see all registered synthetic cases in this demonstration; "
        "production requires authenticated identities and appropriately scoped access.")
st.caption("The external overseer is a proposed governance role. Real independent access, reporting duties "
           "and enforcement powers require an appropriate mandate.")
