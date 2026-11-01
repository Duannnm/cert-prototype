# CERT – Case Evidence Review Tracker: Demonstrator Guide

**Group:** _GroupID_ · **Module:** IS4234 Governance, Regulation and Compliance Technology (NUS, AY2026/27 Sem 1)
**Hosted demonstrator:** _https://….streamlit.app_ (add before export)
**Export as:** `GroupID_Demonstrator_Guide.pdf` (the specification requires more than two pages)

---

## 1. Purpose of the prototype

CERT is a compliance-monitoring workflow for the Post Office Horizon case (focus period 2010–2015). Post Office
Limited (POL) held information suggesting Horizon could be wrong, but no dependable mechanism carried that
information to someone with the independence and authority to stop a decision against a subpostmaster (SPM).
CERT provides that mechanism. It:

* brings case data and supplier-held technical records (PEAKs, KELs, ARQ audit data, remote-intervention logs)
  together, keeping each record's original ID, source file, receipt time and SHA-256 hash;
* shows which required evidence is complete, missing (Gap) or uncertain (Unknown);
* flags potentially relevant defects with an explanation of which fields matched;
* assigns follow-up and escalates delay;
* **blocks reliance on disputed figures** (a recovery demand, or passing figures on as reliable) until
  required inquiries are complete and an independent reviewer with no prior involvement has recorded a reasoned
  decision; and
* re-screens every case, open and closed, whenever a new or updated defect record arrives.

CERT does not decide causation, guilt or disclosure. A defect link is a reason to inquire, not proof. A
non-match is labelled *no known defect identified*, never "Horizon reliable".

## 2. Intended users and the decisions they make

| User | Decision supported in CERT |
|---|---|
| Investigator | What evidence is still needed; which defects require inquiry |
| Supplier liaison manager | Whether requested supplier data was delivered and covers the disputed period |
| Technical reviewer | Whether an expert statement addresses the linked PEAKs/KELs |
| Independent legal reviewer | Whether material must be disclosed, whether reliance may proceed, whether earlier decisions need referral |
| Legal lead (control owner) | How to resolve overdue work and escalated concerns; authorising exceptions only when uninvolved |
| Internal audit / Audit & Risk Committee | Whether controls are operating; where corrective action is required |

## 3. The GRC problem addressed

_Two or three sentences linking to the report: root causes RC2 (no owner of the evidence chain), RC3 (weak
evidence access and preservation) and RC5 (oversight of outputs, not controls), amplified by the presumption that
computers operate correctly. Cite Section 4.2.1 of the report._

How CERT maps to the obligations in report Table 4.5:

| Obligation | CERT control | Evidence produced |
|---|---|---|
| Reasonable inquiry (CPIA Code) | C1 Coverage checklist and reliance gate (Rules 2–3) | Coverage checklist; gap register |
| Disclosure (CPIA s. 3) | C2 Defect linking and independent review (Rules 1, 3) | Explained links; review decision |
| Record retention (CPIA Code) | C3 Versioned, hashed source records | Source versions; audit log |
| Post-conviction duty | C4 Reassessment (Rule 5) | Case screening tasks |
| Expert duties to the court | C5 Expert completeness check (Rule 2) | Check, omissions, corrections |
| Board oversight (COSO; Three Lines) | C6 Escalation and KRIs (Rule 4) | Alerts, dashboard, audit samples |

## 4. Main functions and workflow

A case moves through seven stages, shown as a stepper at the top of every case:

1. **Register** the case and the SPM's explanation.
2. **Link defects** (Rule 1): a potential link is flagged only when the branch is in the defect's scope, the
   defect's *affected* period overlaps the disputed period (not its report date, so later-discovered defects
   still link) and the Horizon version is compatible. Any Unknown field goes to the manual-review queue.
3. **Check coverage** (Rule 2): ARQ audit data for the full disputed period, remote-intervention logs, the
   defect-search result, the SPM's explanation and any expert statement relied on. Partial coverage is a Gap and
   creates a retrieval task for the supplier liaison manager.
4. **Investigate** flags, reasonable alternatives and expert completeness. Missing evidence returns a case here.
5. **Review independently** (Rule 3): the reviewer declares no prior involvement and records a decision with
   reasons. Self-approval is blocked and logged.
6. **Escalate** at any stage (Rule 4): undermining material or a legal deadline within 5 working days goes to
   the legal lead immediately; routine delay goes to the legal lead at 10 and the Audit & Risk Committee at 20
   working days. These are proposed service standards, not statutory periods.
7. **Reassess** (Rule 5) when a new or updated defect record arrives; the original decision is preserved and
   linked.

**Unavailable evidence.** After documented reasonable retrieval, the reviewer may propose an exception recording
the gap, its implications and an action-specific step. It needs confirmation that duties are met and separate
authorisation by an uninvolved legal lead or external legal reviewer. It never bypasses an open required inquiry
and the gap stays visible.

**Screens**

| Screen | What it shows |
|---|---|
| Case list | All cases with stage, gate status, open gaps, open inquiries and escalation; manual-review queue; the user's tasks; case registration |
| Case view | Header, workflow stepper, gate banner stating why reliance is blocked, evidence coverage, defect links, expert check, tasks and escalations, review form, reliance actions and exceptions, supplier evidence, helpline records, case history, evidence-index export |
| Defect records | PEAKs/KELs; upload by CSV or form; Rule 5 results ("X reassessment tasks created") |
| Oversight dashboard | Table 4.4 KRIs with RAG status and "escalates to"; current escalations; gate-attempt counts |
| Audit log & integrity | Filterable append-only log; Verify hashes; Verify audit-log chain |
| About & limitations | Purpose, roles, rules and limitations |

_Insert screenshots: case list, C014 case view, dashboard, Rule 5 result, Verify hashes._

## 5. Software, platform and tools

* **Python 3.12**, **Streamlit 1.66** (web interface), **SQLite** (database), **pandas** (tables), **pytest**
  (tests).
* Hosted on **Streamlit Community Cloud** from a public GitHub repository.
* Rules are transparent Python functions (`rules.py`), not machine learning, so reviewers can see why a link was
  flagged and because no validated training dataset exists.
* Built with assistance from Claude Code (see the AI acknowledgement in the report).

## 6. Accessing the demonstrator

**Hosted (recommended).** Open _link_ in a current browser (Chrome, Edge, Safari or Firefox). No account or
installation is needed. Press **Reset demo data** in the sidebar first so you see the seeded state; the hosted
database is shared by all visitors.

**Locally.**

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py               # opens http://localhost:8501
python evaluation.py               # runs tests, writes test_results.md
```

## 7. Installation and system requirements

* Hosted: any modern browser; a screen at least 1280 px wide is recommended.
* Local: Python 3.11 or later, about 200 MB disk for dependencies, no other services. The database file is
  created automatically in `data/`.

## 8. Test data and demonstration accounts

There are no passwords: the sidebar **role switcher** selects a role and a named user. Every record is
synthetic. The demo clock defaults to **18 Nov 2013**.

| Role | Named users |
|---|---|
| Investigator | A. Tan, R. Shah |
| Supplier liaison manager | M. Okafor |
| Technical reviewer | S. Patel |
| Independent legal reviewer | J. Lim, K. Wong, E. Clarke (external) |
| Legal lead (control owner) | D. Morgan |
| Internal audit / Audit & Risk Committee | H. Ng |

| Case | Scenario |
|---|---|
| C014 | Report Section 4.2.6 (main walkthrough below) |
| C001 | Fully clear case: gate CLEAR, no known defect identified |
| C003 | Closed 2008 Legacy Horizon case caught by a defect loaded in 2013 |
| C005 | Self-approval attempt by the involved investigator, blocked |
| C006 | ARQ request open 25 working days → Committee; rejected exception attempt |
| C007 | Legal deadline 3 working days away → immediate escalation |
| C008 | Horizon version Unknown → manual-review queue |
| C009 | Unavailable evidence, exception validly authorised, gap still visible |
| C010 | Exception authorisation by a conflicted legal lead rejected and escalated |
| C011 | Closed case caught when KEL-D07 is loaded |

`sample_data/KEL-D07_later_defect.csv` can be used to test the CSV upload.

### Suggested walkthrough (case C014)

1. **Case list:** C014 shows BLOCKED, 2 open gaps, 10 WD → Legal lead. Select it.
2. **Case view header:** £4,200 over 1 Apr – 12 May 2013 (6 weeks), Horizon Online v2, Stage 4 Investigate.
3. **Gate banner:** blocked because the ARQ data covers 4 of 6 weeks, the expert statement omits KEL-D01, and
   the independent review referred the material to the prosecutor.
4. **Evidence coverage:** ARQ Gap with retrieval task T-022 for M. Okafor.
5. **Defect links:** KEL-D01 linked on branch, period and version, although reported on 9 Sep 2013; KEL-D02 not
   linked because of a different Horizon version.
6. **Expert check:** XC-001 records the omission of KEL-D01 and a correction request.
7. **Reliance & exceptions:** as A. Tan, press *Issue recovery demand*: blocked, with reasons logged.
8. **Independent review tab:** J. Lim's declaration and decision are recorded against evidence v7.
9. **Self-approval:** switch to Investigator R. Shah, open C005 and record a review: blocked and logged.
10. **Rule 5:** switch to Supplier liaison manager, open *Defect records* and load KEL-D07: two reassessment
    tasks are created, for C014 (linked to decision RV-005) and closed case C011.
11. **Dashboard:** KRIs with red/amber status and escalation targets; move the demo clock forward to watch
    routine items escalate.
12. **Audit log:** *Verify hashes* (all unchanged), then the demo-only out-of-band edit and *Verify hashes*
    again (record ALTERED).

## 9. Known limitations and incomplete functions

* Synthetic data only. Test results (see `test_results.md`) show the rules behave as specified; they cannot
  establish real-world accuracy.
* No real authentication: the role switcher stands in for logins. Production needs identity and role-based
  access control, data minimisation, encryption, retention rules, tested recovery and independent security
  testing.
* Supplier records are uploaded as files; there is no direct supplier integration.
* The demo clock is user-controlled; production needs a trusted time source.
* The hosted database is shared and may be reset by other visitors; it is rebuilt when the app restarts.
* Escalation thresholds and the 10-working-day supplier evidence schedule are proposals to be validated in a
  pilot. Review time and alerts per reviewer per week are not measured.
* The evidence-index export assists, but does not replace, the reviewer's disclosure schedule.
* A hash proves a record is unchanged since receipt, not that it is true. CERT cannot reconstruct evidence
  that was never retained, and cannot create a willingness to act on what it reveals.
