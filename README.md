# CERT – Case Evidence Review Tracker

Technology demonstrator for the IS4234 (NUS, AY2026/27 Sem 1) group project on the Post Office Horizon case.
CERT sits between supplier-held technical records and any decision about an individual subpostmaster (SPM). It
links defects to cases, shows missing evidence, **blocks reliance on disputed figures** until an independent
reviewer has recorded a reasoned decision, escalates delays, and re-screens every past case when a new defect
record arrives.

CERT does **not** decide causation, guilt or disclosure. A defect link means "requires inquiry"; a non-match is
"no known defect identified", never "Horizon reliable". All people, branches and records are fictional.

**Hosted demo:** _add the Streamlit Community Cloud link here_

**Demonstrator Guide:** [docs/GroupID_Demonstrator_Guide.pdf](docs/GroupID_Demonstrator_Guide.pdf) (source:
[docs/Demonstrator_Guide.md](docs/Demonstrator_Guide.md)). It covers the prototype's purpose, users, the GRC
problem and decisions supported, functions and workflow, tools, how to access and run it, requirements, demo
accounts and data, and known limitations.

## Run locally

Requires Python 3.11 or later.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501. On first run it builds `data/cert.db` from the synthetic seed. To rebuild
it at any time, use **Reset demo data** in the sidebar or run `python seed.py`.

## Run the tests and regenerate `test_results.md`

```bash
python evaluation.py
```

This runs the pytest suite (one test per row of report Table 4.6, plus integrity and page-render tests), computes
recall, precision and gate enforcement on the seed data, and writes [`test_results.md`](test_results.md).
`pytest -q` runs the tests alone.

## Deploy to Streamlit Community Cloud

1. Push this folder to a **public** GitHub repository (the `.gitignore` already excludes `.venv/` and `data/`).
2. Go to https://share.streamlit.io, sign in with GitHub and choose **Create app → Deploy a public app from
   GitHub**.
3. Pick the repository and branch, set **Main file path** to `app.py`, open **Advanced settings** and choose
   **Python 3.12**.
4. Deploy. The first visitor's session builds the database from the seed (a few seconds).
5. Copy the `*.streamlit.app` URL into this README and the report, then rebuild the Demonstrator Guide with it
   (next section).

The hosted database is shared by all visitors and is rebuilt whenever the app restarts. Ask markers to press
**Reset demo data** first so they see the seeded state.

## Rebuild the Demonstrator Guide PDF

The guide's text lives in [`docs/Demonstrator_Guide.md`](docs/Demonstrator_Guide.md). Edit that, then rebuild the
PDF (needs `reportlab`, which is documentation tooling only and not in `requirements.txt`):

```bash
pip install reportlab
python docs/build_guide.py --group G1 --url https://your-app.streamlit.app
```

This writes `docs/G1_Demonstrator_Guide.pdf`. Without `--group` and `--url`, the Group ID and hosted link appear
as red placeholders.

## Using the demo

### Navigation, roles and reassessment

Navigation is grouped into **Casework**, **Oversight**, and **Demo & guidance**. Demo walkthrough,
Test results and About & limitations are guidance; Clearance verification is casework.
Pages and operational actions are restricted by the shared `access.py` policy. Mutation services reject
unauthorised calls even if a caller bypasses the UI. Investigators see assigned or involved cases.
Other roles have all registered synthetic cases in this demo; production requires explicit access scope
and authenticated identities. The role switcher is still a presentation tool, not a login system.

Investigators register cases and investigate links. Supplier liaison records deliveries, technical reviewers
check expert evidence, and independent legal reviewers record case decisions. Legal leads manage controls.
**Internal audit (H. Ng)** inspects controls and prepares exports. **Audit & Risk Committee (L. Chen)** handles
Committee escalations. **External independent overseer (P. Evans)** has read-only case, dashboard and audit
access, without operational uploads, reliance, reviewer decisions or demo reset. These are proposed roles,
not claims about a historical POL role or an existing regulator's statutory authority.

For reassessment, CERT screens every registered open and closed case automatically. Investigators/technical
reviewers investigate potential links. Only the assigned uninvolved legal reviewer, different from the
original reviewer, can complete reassessment. An uninvolved legal lead or Committee member can reassign
it, but cannot assign a conflicted or original reviewer. If no eligible reviewer exists, the task stays
unassigned and escalates to the Committee. Existing demo databases receive the new roles and any missing
investigation tasks for pending reassessments without resetting case records.

An outcome of **No referral required** is blocked while other required inquiries or unexcepted evidence
gaps remain. **Refer earlier decision** can preserve uncertainty and creates a required follow-up task for
an uninvolved legal lead (or Committee member). That owner records recipient, receipt reference and the
response/next step. Referral alone does not clear unresolved work or overwrite the original decision.

For the presentation: start as A. Tan, switch to M. Okafor to load KEL-D07, then switch to H. Ng **before**
opening the dashboard/export. For Q&A, inspect a reassessment's named owner and switch to that reviewer.
P. Evans demonstrates read-only independent scrutiny. The full role permission table is in About & limitations.

### Clearance verification and independent oversight

POL staff remain the operational users. **Oversight → Clearance verification** simulates a recovery or legal
system requiring a clearance reference. Requesting one for C014 is refused. C001 can receive a clearance,
which permits only the specified action under its current evidence version and independent review. Verifying
a fabricated reference, a different case/action, or a clearance superseded by evidence or review changes fails.
Issuance and verification are audited. The simulation performs no real recovery or legal action.

**Oversight → Oversight export** lets Internal audit or the Legal lead prepare a ZIP of registered case
snapshots, tasks, decisions, exceptions, gate attempts, defect links, the audit history and integrity checks.
The manifest includes timestamps and file fingerprints. This is a downloadable snapshot, not automatic
regulatory reporting or a signed, externally anchored record. An authorised independent overseer would need
protected delivery, retention and evidence access. Separate recovery/legal registers are required to detect
cases omitted from CERT. Production downstream systems must enforce clearance checking atomically with
their actions, with authenticated access. Optional checks can be bypassed.

The updated **Demo walkthrough** includes these screens within 6:30. Keep the original integrity tampering
exercise for Q&A if time permits. KEL-D07 does not affect C001 and therefore does not invalidate its clearance.

For the presentation, open **Demo & guidance → Demo walkthrough**. It links to each step of the
6:30 demonstration and shows whether KEL-D07 is already loaded. Navigation does not change
roles or load records automatically. Switch roles explicitly in the sidebar.

**Demo & guidance → Test results** displays the saved `test_results.md` evaluation, including its
generation date, denominators, nine scenarios and detailed outcomes. It does not run tests
against the live database. Refresh it locally with `python evaluation.py`, then commit and deploy
the updated report. Case resets do not change the saved evaluation.

The case view now keeps accountable next actions next to the reliance gate. Expand
**Evidence coverage, defect links and expert checks** for the detailed evidence, or use the
task, review and reliance links to reach the relevant controls. Loading a defect shows the
screening summary and links to affected cases, including closed cases.

* **Sidebar:** pick a role and a named user (this stands in for logins), set the **demo clock** (defaults to
  18 Nov 2013) and **Reset demo data**.
* **Case list:** every case with stage, reliance gate (BLOCKED / CLEAR / CLOSED), open gaps and escalations.
  Select a row to open it. Investigators can register new cases here.
* **Case view:** evidence coverage, defect links with explanations, the expert check, the gate banner stating
  why reliance is blocked, tasks and escalations, the review form, reliance actions and exceptions, supplier
  evidence, helpline records and the full case history. **Export evidence index** downloads a CSV.
* **Defect records:** list PEAKs/KELs and add one by CSV upload or form; saving runs Rule 5. The
  *Demo: load the later defect record* tab loads KEL-D07 in one click.
* **Oversight dashboard:** the Table 4.4 key risk indicators with RAG status and escalation targets, current
  escalations and gate-attempt counts.
* **Audit log & integrity:** filterable append-only log, **Verify hashes**, **Verify audit-log chain** and a
  demo-only simulated out-of-band edit.

### Demo users

| Role | Named users |
|---|---|
| Investigator | A. Tan, R. Shah |
| Supplier liaison manager | M. Okafor |
| Technical reviewer | S. Patel |
| Independent legal reviewer | J. Lim, K. Wong, E. Clarke (external) |
| Legal lead (control owner) | D. Morgan |
| Internal audit | H. Ng |
| Audit & Risk Committee | L. Chen |
| External independent overseer | P. Evans |

### Seeded scenarios

| Case | What it shows |
|---|---|
| C014 | Report Section 4.2.6: £4,200 over six weeks; ARQ covers 4 of 6 weeks (Gap + retrieval task); KEL-D01 linked though reported months later; KEL-D02 not linked (different version); expert statement omits KEL-D01; independent review refers material to the prosecutor; recovery blocked. Load KEL-D07 to see Rule 5 create a reassessment task linked to the original decision. |
| C001 | Fully clear case: complete evidence, no known defect identified, independent review permits reliance. |
| C003 | Closed 2008 Legacy Horizon case caught by KEL-D05 (screened regardless of date); reassessment 25 WD old → Committee. |
| C005 | Self-approval attempt by the involved investigator (R. Shah): blocked and logged. |
| C006 | ARQ request open 25 working days → Committee; supplier schedule breached; a rejected exception attempt. |
| C007 | Legal deadline 3 working days away → immediate escalation; remote-intervention logs Unknown. |
| C008 | Horizon version Unknown → manual-review queue. |
| C009 | Unavailable evidence: retrieval documented, exception authorised by an uninvolved legal lead, gap still visible, gate CLEAR. |
| C010 | Exception authorisation by a conflicted legal lead rejected and escalated to the Committee. |
| C011 | Closed case reviewed in 2013; caught by KEL-D07 when it is loaded. |

## Project structure

```
app.py            Entry point: page config, sidebar, Rule 4 sweep, navigation
ui.py             Shared Streamlit helpers (sidebar, styling, tables, gate banner)
views/            Case list, case view, defect records, dashboard, audit log, about
rules.py          Pure rules engine: Rules 1–5 and the expert completeness check (no Streamlit)
services.py       Workflow: applies the rules to the database and writes the audit log
db.py             SQLite schema, SHA-256 source records, append-only hash-chained audit log
seed.py           Synthetic data, replayed through the services on a dated timeline
evaluation.py     Runs the tests, computes metrics, writes test_results.md
tests/            pytest: Table 4.6, integrity and page-render tests
sample_data/      CSVs for the defect upload (KEL-D07 and the seeded extract)
docs/             Demonstrator Guide (Markdown source, PDF, build_guide.py)
```

## Design choice: transparent rules, not machine learning

CERT uses explicit rules so a reviewer can see exactly which fields matched and why an action was blocked, and
because no validated training dataset of PEAKs, KELs and case outcomes exists. The reliance gate is a
human-in-the-loop control: it never approves anything itself; it stops reliance until a qualified, independent
person records a reasoned decision.

## Known limitations

* Synthetic data only; results cannot establish real-world accuracy.
* The role switcher stands in for authentication; production needs identity and role-based access control,
  encryption, retention rules, tested recovery and security testing.
* Supplier records are loaded by file upload; direct supplier integration is a later phase.
* The demo clock is user-controlled; production needs a trusted time source.
* Escalation thresholds and the 10-working-day supplier evidence schedule are proposed service standards, not
  statutory periods.
* A hash proves a record is unchanged since receipt, not that it is true. CERT cannot reconstruct evidence that
  was never retained.
