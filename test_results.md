# CERT – Test results (report Table 4.6 and Section 4.2.7)

Generated 08 Nov 2026 02:10 by `python evaluation.py` · Python 3.14.6 · pytest 9.2.0 · demo date 18 Nov 2013 · synthetic data only.

## Table 4.6 – Test conditions, expected and observed outcomes

| # | Test condition | Expected outcome | Observed outcome (synthetic data) | Result |
|---|---|---|---|---|
| 1 | Relevant defect with overlapping affected period | Link flagged; documented inquiry required | C014 ↔ KEL-D01 Linked on branch, affected period and version although reported months later; inquiry T-024 assigned to the investigator. Loading KEL-D07 opened required inquiry T-036, which the gate lists as a blocker. | **PASSED** |
| 2 | Unrelated branch or incompatible version | No automatic link; explained manual assessment possible | C014 ↔ KEL-D02: No automatic link — “different Horizon version (defect affects Legacy Horizon; case recorded on Horizon Online v2)”; no task created. Branch 117 vs KEL-D01: outside scope. C001 reported as “No known defect identified”, never as reliable. | **PASSED** |
| 3 | Missing audit period or unknown field | Gap or uncertainty shown; follow-up task assigned | C014 ARQ shown as Gap (“4 of 6 weeks received; missing 29 Apr – 12 May 2013”); retrieval T-022 assigned to M. Okafor (supplier liaison). C008 version Unknown → manual-review queue (T-031), defect search Unknown. C007 remote-intervention logs Unknown with a confirmation task. | **PASSED** |
| 4 | Defect learned after a decision | Reassessment tasks created for closed and earlier cases | Rule 5 re-screened 10 cases (open and closed, regardless of date): 2 potential link(s), 0 manual-review item(s), 2 reassessment task(s) created. Tasks T-035 (closed C011) and T-037 (C014) link to original decisions RV-001 and RV-005, which are unchanged. Seeded KEL-D05 caught closed 2008 Legacy Horizon case C003. | **PASSED** |
| 5 | Self-approval or open inquiry at reliance gate | Approval blocked and reason recorded | R. Shah (involved investigator) self-approval on C005 blocked and logged as a self-review attempt. “Reliance may proceed” on C014 by uninvolved K. Wong blocked while the ARQ gap and expert correction are open; recovery demand on C014 blocked. Control: K. Wong's review of C005 was accepted and the gate turned CLEAR. | **PASSED** |
| 6 | Overdue request or imminent deadline | Correct routine or immediate escalation generated | Boundaries: 9 WD none, 10 WD → legal lead, 20 WD → Committee, deadline 5 WD away → immediate, 6 WD away → none. Seed at 18 Nov 2013: C006 ARQ request (25 WD) → Committee; C014 ARQ request (17 WD) → legal lead; C007 deadline 21 Nov (3 WD) → immediate. 8 escalations logged. | **PASSED** |
| 7 | Expert statement omits a relevant known defect | Record omission; require correction and independent assessment; keep gate blocked | Check XC-001 recorded omission of KEL-D01 in ES-014 v1 and opened T-025; gate blocked with the omission as a reason. After v2 addressed KEL-D01 the correction closed, but the gate stayed blocked on the ARQ gap and the review decision. | **PASSED** |
| 8 | Unavailable evidence after reasonable retrieval | Retain gap; require action-specific reasons and separate authorisation | C009 ARQ stays “Gap” after retrieval was documented as exhausted; EX-001 proposed by J. Lim and separately authorised by D. Morgan; gate CLEAR only under the exception, gap still shown. A proposal without implications, action, reasons or duty confirmation is rejected. EX-002 authorised by external reviewer E. Clarke leaves the C010 gap visible and still requires a review. | **PASSED** |
| 9 | Exception attempted with an open inquiry or conflicted authoriser | Reject exception; record attempt and escalate | Seeded: K. Wong's C006 proposal (retrieval still open) rejected and escalated to the legal lead; D. Morgan's C010 authorisation rejected as conflicted and escalated to the Audit & Risk Committee. Live: J. Lim's C014 proposal rejected (open ARQ request), logged and escalated. A proposer authorising their own exception is rejected. | **PASSED** |

## Effectiveness metrics

| Metric | Target | Result | Notes |
|---|---|---|---|
| Recall (seeded relevant links flagged) | 100% | 100% (5/5) | After Rule 5 loads KEL-D07; seed alone 100% (3/3). Manual-review items count as flagged. |
| Precision (flags judged relevant) | Monitored, no target | 83% (5/6) | Not relevant: C006 ↔ PEAK-P08 (cosmetic print defect; matched on scope, period and version, then closed on inquiry). Seed alone 75% (3/4). |
| Gate enforcement (prohibited actions blocked) | 100% | 100% (38/38) | Every blocked attempt is logged in `gate_attempts` and the audit log. |
| Permitted actions allowed (control) | — | 100% (3/3) | Shows the gate is not simply blocking everything. |
| Review time; alerts per reviewer per week | — | Not measured | Needs real reviewers in a pilot. |

## Gate-enforcement battery

| Scenario | Prohibited? | Outcome | First reason recorded |
|---|---|---|---|
| C001: self-approval by involved A. Tan | Yes | Blocked | Self-approval blocked: A. Tan is recorded as involved in this case |
| C003: Issue recovery demand while gate BLOCKED | Yes | Blocked | Closed case under reassessment: further reliance on the original figures (e.g. continued recovery) is suspended until the reassessment is decided |
| C003: Pass figures on as reliable (prosecution / disclosure) while gate BLOCKED | Yes | Blocked | Closed case under reassessment: further reliance on the original figures (e.g. continued recovery) is suspended until the reassessment is decided |
| C005: Issue recovery demand while gate BLOCKED | Yes | Blocked | No independent review recorded: a reviewer with no prior involvement must record a reasoned decision |
| C005: Pass figures on as reliable (prosecution / disclosure) while gate BLOCKED | Yes | Blocked | No independent review recorded: a reviewer with no prior involvement must record a reasoned decision |
| C005: self-approval by involved R. Shah | Yes | Blocked | Self-approval blocked: R. Shah is recorded as involved in this case |
| C006: Issue recovery demand while gate BLOCKED | Yes | Blocked | ARQ audit data — Gap: 0 of 6 weeks received; missing 19 Aug – 29 Sep 2013 (follow-up T-015 with M. Okafor) |
| C006: Pass figures on as reliable (prosecution / disclosure) while gate BLOCKED | Yes | Blocked | ARQ audit data — Gap: 0 of 6 weeks received; missing 19 Aug – 29 Sep 2013 (follow-up T-015 with M. Okafor) |
| C006: self-approval by involved A. Tan | Yes | Blocked | Self-approval blocked: A. Tan is recorded as involved in this case |
| C006: “Reliance may proceed” by uninvolved K. Wong while blockers remain | Yes | Blocked | “Reliance may proceed” cannot be recorded while 1 blocker remains: |
| C006: exception proposed while a required inquiry is open | Yes | Blocked | An exception cannot bypass an open required inquiry (T-015) |
| C007: Issue recovery demand while gate BLOCKED | Yes | Blocked | Remote-intervention logs — Unknown: Supplier has not confirmed whether these records exist for the disputed period (follow-up T-030 with M. Okafor) |
| C007: Pass figures on as reliable (prosecution / disclosure) while gate BLOCKED | Yes | Blocked | Remote-intervention logs — Unknown: Supplier has not confirmed whether these records exist for the disputed period (follow-up T-030 with M. Okafor) |
| C007: self-approval by involved R. Shah | Yes | Blocked | Self-approval blocked: R. Shah is recorded as involved in this case |
| C007: “Reliance may proceed” by uninvolved K. Wong while blockers remain | Yes | Blocked | “Reliance may proceed” cannot be recorded while 1 blocker remains: |
| C007: exception proposed while a required inquiry is open | Yes | Blocked | An exception cannot bypass an open required inquiry (T-030) |
| C008: Issue recovery demand while gate BLOCKED | Yes | Blocked | Defect-search result — Unknown: Manual review pending for KEL-D01 (a required field is Unknown) (follow-up T-031 with A. Tan) |
| C008: Pass figures on as reliable (prosecution / disclosure) while gate BLOCKED | Yes | Blocked | Defect-search result — Unknown: Manual review pending for KEL-D01 (a required field is Unknown) (follow-up T-031 with A. Tan) |
| C008: self-approval by involved A. Tan | Yes | Blocked | Self-approval blocked: A. Tan is recorded as involved in this case |
| C008: “Reliance may proceed” by uninvolved K. Wong while blockers remain | Yes | Blocked | “Reliance may proceed” cannot be recorded while 1 blocker remains: |
| C008: exception proposed while a required inquiry is open | Yes | Blocked | An exception cannot bypass an open required inquiry (T-031) |
| C009: self-approval by involved R. Shah | Yes | Blocked | Self-approval blocked: R. Shah is recorded as involved in this case |
| C010: Issue recovery demand while gate BLOCKED | Yes | Blocked | ARQ audit data — Gap: 4 of 6 weeks received; missing 4 Mar – 17 Mar 2013 (supplier reports the missing records unavailable) |
| C010: Pass figures on as reliable (prosecution / disclosure) while gate BLOCKED | Yes | Blocked | ARQ audit data — Gap: 4 of 6 weeks received; missing 4 Mar – 17 Mar 2013 (supplier reports the missing records unavailable) |
| C010: self-approval by involved A. Tan | Yes | Blocked | Self-approval blocked: A. Tan is recorded as involved in this case |
| C010: self-approval by involved D. Morgan | Yes | Blocked | Self-approval blocked: D. Morgan is recorded as involved in this case |
| C010: “Reliance may proceed” by uninvolved K. Wong while blockers remain | Yes | Blocked | “Reliance may proceed” cannot be recorded while 1 blocker remains: |
| C011: Issue recovery demand while gate BLOCKED | Yes | Blocked | Closed case under reassessment: further reliance on the original figures (e.g. continued recovery) is suspended until the reassessment is decided |
| C011: Pass figures on as reliable (prosecution / disclosure) while gate BLOCKED | Yes | Blocked | Closed case under reassessment: further reliance on the original figures (e.g. continued recovery) is suspended until the reassessment is decided |
| C014: Issue recovery demand while gate BLOCKED | Yes | Blocked | ARQ audit data — Gap: 4 of 6 weeks received; missing 29 Apr – 12 May 2013 (follow-up T-022 with M. Okafor) |
| C014: Pass figures on as reliable (prosecution / disclosure) while gate BLOCKED | Yes | Blocked | ARQ audit data — Gap: 4 of 6 weeks received; missing 29 Apr – 12 May 2013 (follow-up T-022 with M. Okafor) |
| C014: self-approval by involved A. Tan | Yes | Blocked | Self-approval blocked: A. Tan is recorded as involved in this case |
| C014: “Reliance may proceed” by uninvolved K. Wong while blockers remain | Yes | Blocked | “Reliance may proceed” cannot be recorded while 4 blockers remain: |
| C014: exception proposed while a required inquiry is open | Yes | Blocked | An exception cannot bypass an open required inquiry (T-022, T-025, T-036, T-037) |
| C005: review recorded by uninvolved investigator A. Tan (role not authorised) | Yes | Blocked | The role “Investigator” cannot record an independent review |
| C005: reviewer omits the conflict declaration | Yes | Blocked | No conflict declaration: the reviewer must declare no prior involvement |
| C010: EX-002 authorised by conflicted legal lead D. Morgan | Yes | Blocked | Conflicted authoriser: D. Morgan is recorded as involved in this case |
| C010: EX-002 authorised by its proposer K. Wong | Yes | Blocked | Only an uninvolved legal lead or an external legal reviewer may authorise an exception |
| C001: Issue recovery demand with gate CLEAR | No | Permitted | Issue recovery demand: permitted by the reliance gate |
| C009: Issue recovery demand with gate CLEAR | No | Permitted | Issue recovery demand: permitted by the reliance gate |
| C010: EX-002 authorised by uninvolved external reviewer E. Clarke | No | Permitted | Exception EX-002 authorised. The gap remains visible on the case. |

## Supporting tests

| Test | Result |
|---|---|
| `test_clearance_requires_clear_gate_and_authorised_role` | **PASSED** |
| `test_clearance_checks_case_action_and_reference` | **PASSED** |
| `test_later_evidence_invalidates_clearance` | **PASSED** |
| `test_new_review_invalidates_old_clearance` | **PASSED** |
| `test_oversight_export_permissions_and_fingerprints` | **PASSED** |
| `test_clearance_page_rejects_c014_and_accepts_c001` | **PASSED** |
| `test_oversight_page_prepares_snapshot_for_auditor` | **PASSED** |
| `test_audit_log_is_append_only_and_chained` | **PASSED** |
| `test_source_record_hash_detects_out_of_band_change` | **PASSED** |
| `test_wording_never_claims_cause_or_reliability` | **PASSED** |
| `test_metrics_meet_design_targets` | **PASSED** |
| `test_page_renders[views/case_list.py]` | **PASSED** |
| `test_page_renders[views/case_view.py]` | **PASSED** |
| `test_page_renders[views/defects.py]` | **PASSED** |
| `test_page_renders[views/dashboard.py]` | **PASSED** |
| `test_page_renders[views/audit_log.py]` | **PASSED** |
| `test_page_renders[views/about.py]` | **PASSED** |
| `test_page_renders[views/demo.py]` | **PASSED** |
| `test_page_renders[views/test_results.py]` | **PASSED** |
| `test_page_renders[views/clearance.py]` | **PASSED** |
| `test_page_renders[views/oversight_export.py]` | **PASSED** |
| `test_case_view_renders[C001]` | **PASSED** |
| `test_case_view_renders[C003]` | **PASSED** |
| `test_case_view_renders[C005]` | **PASSED** |
| `test_case_view_renders[C006]` | **PASSED** |
| `test_case_view_renders[C007]` | **PASSED** |
| `test_case_view_renders[C008]` | **PASSED** |
| `test_case_view_renders[C009]` | **PASSED** |
| `test_case_view_renders[C010]` | **PASSED** |
| `test_case_view_renders[C011]` | **PASSED** |
| `test_case_view_renders[C014]` | **PASSED** |
| `test_saved_report_metrics_and_scenarios` | **PASSED** |
| `test_missing_report_explains_refresh` | **PASSED** |
| `test_case_deep_link_selects_reliance_tab` | **PASSED** |
| `test_results_page_shows_saved_evidence` | **PASSED** |
| `test_loading_later_defect_reports_two_reassessments` | **PASSED** |

## Interpretation

These targets are design standards, not legal thresholds. The cases, defects and expected links were written by the project team, so the results show that the rules behave as specified; they cannot establish accuracy on real PEAKs, KELs or case files. A pilot would add review time, alert volume per reviewer and audit sampling of closed flags, exceptions and no-match cases.
