"""Responsibilities, rationale and actual page access for each simulated role."""
import streamlit as st

import access
import services as S
import ui
import presentation_roles

ui.require_page("roles")
ui.header("Roles", "Responsibilities, separation of duties and access to CERT")
st.write("Five roles explain the workflow: investigate, supply evidence, review independently, "
         "audit controls and scrutinise externally.")

pages = [("case_list", "Case list"), ("case_view", "Case view"),
         ("defects", "Defect records"), ("clearance", "Clearance verification"),
         ("dashboard", "Oversight dashboard"), ("oversight_export", "Oversight export"),
         ("audit_log", "Audit log & integrity")]
rows = []
for role, responsibility, why, limits in presentation_roles.PROFILES:
    actor = S.Actor("role-guide", "Role guide", role)
    rows.append({"role": role, "responsibility": responsibility, "why": why,
                 "pages": "; ".join(title for page, title in pages if access.page_allowed(actor, page)),
                 "limits": limits})
ui.table(rows, [("role", "Role"), ("responsibility", "Responsibilities"),
                ("why", "Why this role is needed"), ("pages", "Accessible pages"),
                ("limits", "Actions and boundaries")])
st.caption("All five roles can also open Roles, Test results and About & limitations. "
           "Accessible casework/oversight pages are calculated from CERT’s permission policy. Opening a case page does not "
           "grant every action on it; role, case scope, task assignment and conflict checks still apply.")
st.info("The sidebar role switcher simulates identity; it is not authentication. Investigators are POL staff "
        "or act on POL’s behalf. Other roles see all registered synthetic cases in this demonstration; "
        "production requires authenticated identities and appropriately scoped access.")
st.caption("The external overseer is a proposed governance role. Real independent access, reporting duties "
           "and enforcement powers require an appropriate mandate.")
st.caption("Technical checks and escalation recipients remain named in case records. They are supporting "
           "responsibilities, not additional selectable roles in this presentation.")
