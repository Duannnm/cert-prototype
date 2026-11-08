"""Shared permissions for the simulated identities. This is not authentication."""
import rules as R

PERMISSIONS = {
    "register_case": (R.INVESTIGATOR,),
    "import_legacy_case": (R.LEGAL_LEAD,),
    "load_defect": (R.SUPPLIER_LIAISON, R.TECH_REVIEWER, R.LEGAL_LEAD),
    "load_complaints": (R.INVESTIGATOR, R.LEGAL_LEAD),
    "record_supplier_delivery": (R.SUPPLIER_LIAISON,),
    "close_retrieval_unavailable": (R.SUPPLIER_LIAISON, R.LEGAL_LEAD),
    "record_inquiry_outcome": (R.INVESTIGATOR, R.TECH_REVIEWER),
    "record_expert_statement": (R.TECH_REVIEWER,),
    "run_expert_check": (R.TECH_REVIEWER,),
    "record_review": (R.LEGAL_REVIEWER,),
    "attempt_reliance": (R.INVESTIGATOR, R.LEGAL_REVIEWER, R.LEGAL_LEAD),
    "issue_clearance": (R.INVESTIGATOR, R.LEGAL_REVIEWER, R.LEGAL_LEAD),
    "verify_clearance": (R.INVESTIGATOR, R.LEGAL_REVIEWER, R.LEGAL_LEAD),
    "propose_exception": (R.LEGAL_REVIEWER,),
    "authorise_exception": (R.LEGAL_LEAD, R.LEGAL_REVIEWER),
    "acknowledge_escalation": (R.LEGAL_LEAD, R.COMMITTEE),
    "complete_reassessment": (R.LEGAL_REVIEWER,),
    "assign_reassessment": (R.LEGAL_LEAD, R.COMMITTEE),
    "record_referral_followup": (R.LEGAL_LEAD, R.COMMITTEE),
    "refresh_case": (R.LEGAL_LEAD,),
    "close_case": (R.LEGAL_LEAD,),
    "simulate_tampering": (R.AUDIT,),
    "oversight_export": (R.AUDIT, R.LEGAL_LEAD),
    "oversight": (R.LEGAL_LEAD, R.AUDIT, R.COMMITTEE, R.OVERSEER),
}


def allows(actor, operation):
    return actor.role in PERMISSIONS.get(operation, ())


def page_allowed(actor, page):
    if page in ("demo", "test_results", "about", "case_list", "case_view"):
        return actor.role in R.ROLES
    return allows(actor, {"defects": "load_defect", "clearance": "issue_clearance",
                          "oversight_export": "oversight_export",
                          "dashboard": "oversight", "audit_log": "oversight"}.get(page, ""))
