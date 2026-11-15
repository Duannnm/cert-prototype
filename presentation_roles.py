"""The five interactive roles used to explain the prototype.

Supporting technical/control owners remain on historical records and escalations;
they are not additional presenter identities and their permissions are not merged.
"""
import rules as R

PROFILES = (
    (R.INVESTIGATOR, "Investigate assigned cases and request/verify clearance.",
     "Connect the SPM’s account to evidence and accountable follow-up.",
     "Assigned/involved cases only; cannot record independent legal approval."),
    (R.SUPPLIER_LIAISON, "Load defect records and record supplier evidence deliveries.",
     "Bring supplier knowledge into casework and trigger retrospective screening.",
     "Cannot approve reliance or complete independent legal review."),
    (R.LEGAL_REVIEWER, "Record independent case decisions and complete assigned reassessments.",
     "Prevent investigators approving their own work; assess effects on earlier decisions.",
     "Must be uninvolved; cannot reassess their own earlier decision."),
    (R.AUDIT, "Inspect control indicators, audit records and prepare oversight exports.",
     "Test control operation and make the evidence available for scrutiny.",
     "Cannot approve reliance or alter operational casework."),
    (R.OVERSEER, "Read cases, oversight indicators and audit evidence.",
     "Provide scrutiny outside POL’s operational decision-making.",
     "Read-only; cannot edit cases, issue clearance or prepare exports."),
)
ROLES = tuple(profile[0] for profile in PROFILES)
