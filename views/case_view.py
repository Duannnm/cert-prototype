import pandas as pd
import streamlit as st

import rules as R
import services as S
import ui

conn = ui.conn()
cases = S.visible_cases(conn, ui.actor())
ids = [c["case_id"] for c in cases]
if not ids:
    st.info("No cases are assigned to this investigator yet.")
    st.stop()
requested = st.query_params.get("case") or st.session_state.get("case_id") or "C014"
if requested not in ids:
    if st.query_params.get("case"):
        st.warning("This case is outside your permitted scope. Choose one of your assigned cases.")
        st.page_link("views/case_list.py", label="Open your case list")
        st.stop()
    requested = ids[0]

top_l, top_r = st.columns([3, 1])
with top_l:
    labels = {c["case_id"]: f"{c['case_id']} – {c['branch']} {c['branch_name']}" for c in cases}
    case_id = st.selectbox("Case", ids, index=ids.index(requested), format_func=labels.get)
if case_id != st.query_params.get("case"):
    st.query_params["case"] = case_id
st.session_state["case_id"] = case_id

case = S.get_case(conn, case_id)
gate = S.case_gate(conn, case_id)
items = S.evidence_items(conn, case_id)
links = S.case_links(conn, case_id)
tasks = S.case_tasks(conn, case_id)
open_tasks = [t for t in tasks if t["status"] == "Open"]
escalations = {t["task_id"]: S.task_escalation(t, case, ui.today()) for t in open_tasks}
escalated = any(e.level != R.ESC_NONE for e in escalations.values())
me = ui.actor()

with top_r:
    st.write("")
    index = pd.DataFrame(S.evidence_index(conn, case_id))
    st.download_button("Export evidence index (CSV)", index.to_csv(index=False).encode("utf-8"),
                       file_name=f"{case_id}_evidence_index.csv", mime="text/csv", width="stretch",
                       help="Assists, but does not replace, the reviewer's preparation of disclosure schedules.")

ui.header(f"Case {case_id} | Branch {case['branch']} {case['branch_name']}",
          f"Synthetic demonstration · demo date {R.fmt_date(ui.today())}")
ui.render_flash()

start, end = R.parse_date(case["disputed_start"]), R.parse_date(case["disputed_end"])
span = f" ({R.span_text((end - start).days + 1)})" if start and end else ""
facts = [("Disputed shortfall", ui.money(case["amount"])),
         ("Disputed period", R.fmt_range(case["disputed_start"], case["disputed_end"]) + span),
         ("Horizon version", case["horizon_version"]),
         ("Status", f"{case['status'].capitalize()} · Stage {case['stage']} {ui.STAGES[case['stage'] - 1]}"),
         ("Evidence version", f"v{case['evidence_version']}")]
if case["legal_deadline"]:
    facts.append(("Legal deadline", f"{R.fmt_date(case['legal_deadline'])} – {case['legal_deadline_note'] or ''}"))
ui.kv(facts)
ui.stepper(case["stage"], escalated, case["status"] == "closed")
ui.gate_banner(gate)

st.subheader("Next actions and accountable owners")
required = [t for t in open_tasks if t["required"] or t["type"] == "Independent review"]
if required:
    ui.table([{"task": t["task_id"], "action": t["title"],
               "owner": S.user_name(conn, t["owner"]),
               "escalation": escalations[t["task_id"]].label,
               "decision": t["linked_to"] or "—"} for t in required],
             [("task", "Task"), ("action", "Required next action"), ("owner", "Accountable owner"),
              ("escalation", "Escalation"), ("decision", "Earlier decision")])
else:
    st.caption("No required follow-up task is open. The reliance gate still determines whether an action is permitted.")
if gate.blocked:
    st.caption("An uninvolved independent legal reviewer must assess the current evidence and record a reasoned "
               "decision before reliance can proceed. Completing tasks alone does not clear the gate.")
st.markdown("[Open task actions](?case=" + case_id + "&tab=tasks#case-actions) · "
            "[Open review](?case=" + case_id + "&tab=review#case-actions) · "
            "[Open reliance controls](?case=" + case_id + "&tab=reliance#case-actions)")

if case["spm_explanation"]:
    st.markdown(f"<div class='quote'><b>SPM explanation.</b> {ui.esc(case['spm_explanation'])}</div>",
                unsafe_allow_html=True)

with st.expander("Evidence coverage, defect links and expert checks", expanded=False):
    # --- Evidence coverage (Rule 2) -----------------------------------------------------
    st.subheader("Evidence coverage")
    st.caption("Rule 2 checklist. Partial coverage of the disputed period is a Gap; Unknown is never dropped.")
    follow = {t["item_type"]: t for t in open_tasks if t["item_type"]}
    exceptions = {e["item_type"]: e for e in S.case_exceptions(conn, case_id)}
    rows = []
    for i in items:
        task = follow.get(i["item_type"])
        note = f"{task['task_id']} · {S.user_name(conn, task['owner'])}" if task else ""
        ex = exceptions.get(i["item_type"])
        if ex and i["status"] in (R.GAP, R.UNKNOWN):
            note = (note + "; " if note else "") + f"Exception {ex['exception_id']} {ex['status'].lower()}"
        rows.append({"item": i["item_type"], "status": ui.chip(i["status"]), "period": i["period_covered"],
                     "reason": i["reason"], "owner": i["owner"], "follow": note})
    ui.table(rows, [("item", "Required item"), ("status", "Status"), ("period", "Period covered / scope"),
                    ("reason", "Reason"), ("owner", "Owner"), ("follow", "Follow-up")], raw=("status",),
             nowrap=("item", "status"), wide=("reason",))

    # --- Defect links (Rule 1) ------------------------------------------------------------
    st.subheader("Defect links")
    st.caption("Rule 1 matches branch scope, the defect's affected period (not its report date) and Horizon version. "
               "A link requires inquiry; it does not establish causation.")
    if not any(l["result"] != R.NO_MATCH for l in links):
        st.markdown(f"{ui.chip(R.NO_KNOWN_DEFECT, 'grey')} <span class='muted'>This is not confirmation that "
                    "Horizon was reliable: records may be incomplete or faults unknown.</span>", unsafe_allow_html=True)
    ui.table([{"defect": l["defect_id"], "result": ui.chip(R.RESULT_LABELS[l["result"]], ui.KIND[l["result"]]),
               "matched": ", ".join(l["matched_fields"]) or "—", "explanation": l["explanation"],
               "inquiry": l["inquiry_status"] + (f": {l['inquiry_finding']}" if l["inquiry_finding"] else "")}
              for l in links],
             [("defect", "Defect"), ("result", "Result"), ("matched", "Fields matched"),
              ("explanation", "Explanation"), ("inquiry", "Inquiry")], raw=("result",), nowrap=("defect", "result"),
             wide=("explanation",))

    # --- Expert completeness check -------------------------------------------------------
    st.subheader("Expert completeness check")
    statements = S.statements(conn, case_id)
    checks = S.expert_checks(conn, case_id)
    if not statements:
        st.markdown("<div class='muted'>No expert statement is relied on in this case.</div>", unsafe_allow_html=True)
    else:
        ui.table([{"st": f"{s['statement_id']} v{s['version']}", "author": s["author"],
                   "addr": ", ".join(s["linked_defects"]) or "none", "summary": s["summary"],
                   "on": ui.short_ts(s["submitted_on"])} for s in statements],
                 [("st", "Statement"), ("author", "Author"), ("addr", "Defects addressed"), ("summary", "Summary"),
                  ("on", "Received")], nowrap=("st", "on"))
        ui.table([{"id": c["check_id"], "st": f"{c['statement_id']} v{c['statement_version']}",
                   "by": S.user_name(conn, c["checker"]), "rel": ", ".join(c["relevant_defects"]) or "none",
                   "om": ui.chip("Omits " + ", ".join(c["omissions"]), "amber") if c["omissions"] else ui.chip("None", "green"),
                   "status": c["correction_status"], "on": ui.short_ts(c["checked_on"])} for c in checks],
                 [("id", "Check"), ("st", "Statement"), ("by", "Technical reviewer"), ("rel", "Linked defects compared"),
                  ("om", "Omissions"), ("status", "Correction"), ("on", "Date")], raw=("om",), nowrap=("id", "on"))

# --- Tabs ------------------------------------------------------------------------------
st.markdown('<div id="case-actions"></div>', unsafe_allow_html=True)
requested_tab = st.query_params.get("tab")
tab_names = {"tasks": "Tasks & escalation", "review": "Independent review", "reliance": "Reliance & exceptions"}
if requested_tab in tab_names:
    st.session_state["case_tabs"] = tab_names[requested_tab]
    del st.query_params["tab"]
t_tasks, t_review, t_rely, t_supply, t_expert, t_help, t_hist = st.tabs([
    "Tasks & escalation", "Independent review", "Reliance & exceptions",
    "Supplier evidence", "Expert statement actions", "Helpline records", "Case history"], key="case_tabs")

with t_tasks:
    st.caption("Rule 4: material that may undermine an active case, or a legal deadline within 5 working days, "
               "escalates immediately; routine delay escalates at 10 and 20 working days (proposed standards).")
    trows = []
    for t in tasks:
        esc = escalations.get(t["task_id"])
        trows.append({
            "id": t["task_id"], "type": t["type"], "title": t["title"], "owner": S.user_name(conn, t["owner"]),
            "created": ui.short_ts(t["created"]), "age": f"{esc.age_wd} WD" if esc else "",
            "esc": ui.chip(esc.label, ui.KIND[esc.level]) if esc and esc.level != R.ESC_NONE else "",
            "status": ui.chip("Open") if t["status"] == "Open" else
            ui.chip(f"Closed · {t['outcome']}", "grey"),
            "linked": t["linked_to"] or ""})
    st.markdown(f"**{len(open_tasks)} open** of {len(tasks)} tasks")
    ui.table(trows, [("id", "ID"), ("type", "Type"), ("title", "Task"), ("owner", "Owner"),
                     ("created", "Created"), ("age", "Age"), ("esc", "Escalation"), ("status", "Status"),
                     ("linked", "Linked to")], raw=("esc", "status"),
             nowrap=("id", "created", "age"), wide=("title",))

    for t in [t for t in open_tasks if t["type"] == "Reassessment"]:
        with st.container(border=True):
            st.markdown(f"**{t['task_id']} – {t['title']}**")
            st.markdown(f"<div class='quote'>{ui.esc(t['detail']).replace(chr(10), '<br>')}</div>",
                        unsafe_allow_html=True)

    inquiries = [t for t in open_tasks if t["type"] in ("Defect inquiry", "Manual review")]
    if inquiries:
        st.markdown("**Record an inquiry outcome**")
        if ui.allowed(R.INVESTIGATOR, R.TECH_REVIEWER, action="record an inquiry outcome"):
            with st.form("inquiry"):
                task_id = st.selectbox("Inquiry", [t["task_id"] for t in inquiries],
                                       format_func=lambda x: next(f"{x} – {t['title']}" for t in inquiries
                                                                  if t["task_id"] == x))
                outcome = st.radio("Outcome", [S.INQUIRY_RELEVANT, S.INQUIRY_NOT_RELEVANT], horizontal=True)
                finding = st.text_area("Finding (symptoms compared with branch transactions; technical advice)")
                undermine = st.checkbox("This material may undermine the case (immediate escalation to the legal lead)")
                if st.form_submit_button("Record outcome", type="primary"):
                    ui.flash(S.record_inquiry_outcome(conn, me, ui.now(), task_id, outcome=outcome,
                                                      finding=finding, may_undermine=undermine))

    open_esc = [t for t in open_tasks if t["type"] == "Escalation"]
    if open_esc:
        st.markdown("**Resolve an escalation**")
        if ui.allowed(R.LEGAL_LEAD, R.COMMITTEE, action="resolve escalations"):
            with st.form("escalation"):
                task_id = st.selectbox("Escalation", [t["task_id"] for t in open_esc],
                                       format_func=lambda x: next(f"{x} – {t['title']}" for t in open_esc
                                                                  if t["task_id"] == x))
                note = st.text_input("Action taken")
                if st.form_submit_button("Acknowledge and record action", type="primary"):
                    ui.flash(S.acknowledge_escalation(conn, me, ui.now(), task_id, note))

    reassess = [t for t in open_tasks if t["type"] == "Reassessment"]
    referral_tasks = [t for t in open_tasks if t["type"] == "Referral follow-up"]
    if referral_tasks and ui.can("record_referral_followup"):
        with st.form("referral_followup"):
            st.markdown("**Record referral receipt and follow-through**")
            task_id = st.selectbox("Referral task", [t["task_id"] for t in referral_tasks])
            evidence = st.text_area("Recipient, receipt reference, response or documented next step")
            if st.form_submit_button("Record referral follow-through"):
                ui.flash(S.record_referral_followup(conn, me, ui.now(), task_id, evidence))
    if reassess:
        st.caption("CERT screens cases automatically. Investigators and technical reviewers investigate the link; "
                   "the assigned uninvolved legal reviewer reassesses the earlier decision. The original reviewer "
                   "cannot complete their own reassessment. Referral may record unresolved concerns; no-referral "
                   "closure requires the other required inquiries and evidence gaps to be resolved.")
        if ui.can("assign_reassessment"):
            with st.form("assign_reassessment"):
                task_id = st.selectbox("Task to assign", [t["task_id"] for t in reassess])
                candidates = [u for u in S.list_users(conn) if u.role == R.LEGAL_REVIEWER]
                reviewer = st.selectbox("Assign independent reviewer", [u.user_id for u in candidates],
                                        format_func=lambda uid: S.user_name(conn, uid))
                if st.form_submit_button("Assign reviewer"):
                    ui.flash(S.assign_reassessment(conn, me, ui.now(), task_id, reviewer))
        st.markdown("**Complete a reassessment** (the original decision is preserved unchanged)")
        if ui.allowed(R.LEGAL_REVIEWER, action="complete a reassessment"):
            with st.form("reassess"):
                mine = [t["task_id"] for t in reassess if t["owner"] == me.user_id]
                if not mine:
                    st.info("No reassessment here is assigned to you. Ask an uninvolved legal lead or Committee member to assign it.")
                task_id = st.selectbox("Reassessment", mine)
                outcome = st.radio("Outcome", [S.REASSESS_REFER, S.REASSESS_NO_REFERRAL])
                reasons = st.text_area("Reasons")
                declared = st.checkbox("I declare no prior involvement in this case")
                if st.form_submit_button("Record reassessment", type="primary", disabled=not mine):
                    ui.flash(S.complete_reassessment(conn, me, ui.now(), task_id, outcome=outcome, reasons=reasons,
                                                     declared_no_involvement=declared))

with t_review:
    reviews = S.case_reviews(conn, case_id)
    ui.table([{"id": r["review_id"], "by": "Legacy file (pre-CERT)" if r["is_historical"] else S.user_name(conn, r["reviewer"]),
               "decl": r["conflict_declaration"], "ver": f"v{r['evidence_version']}" if not r["is_historical"] else "—",
               "decision": r["decision"], "reasons": r["reasons"],
               "exc": f"{r['exception_id']} (authorised by {S.user_name(conn, r['exception_authoriser'])})"
               if r["exception_flag"] else "", "on": ui.short_ts(r["recorded_on"])} for r in reviews],
             [("id", "Review"), ("by", "Reviewer"), ("decl", "Conflict declaration"), ("ver", "Evidence"),
              ("decision", "Decision"), ("reasons", "Reasons"), ("exc", "Exception"), ("on", "Date")],
             nowrap=("id", "on"))
    if case["status"] == "active" and ui.can("record_review"):
        st.markdown("**Record an independent review (Stage 5)**")
        involved = ", ".join(S.user_name(conn, u) for u in case["involved_users"])
        st.caption(f"Human-in-the-loop control: only an independent legal reviewer with no prior involvement may "
                   f"record a decision. Recorded as involved: {involved}. Self-approval attempts are blocked, "
                   "logged and reported to internal audit.")
        with st.form("review"):
            st.markdown(f"Reviewer: **{me.label}** · evidence version **v{case['evidence_version']}**")
            declared = st.checkbox("I declare that I have had no prior involvement in this case")
            conflict_note = st.text_input("Declaration note (optional)")
            decision = st.selectbox("Decision", R.REVIEW_DECISIONS)
            reasons = st.text_area("Reasons (address contrary evidence and explain remaining uncertainty)")
            if st.form_submit_button("Record review", type="primary"):
                ui.flash(S.record_review(conn, me, ui.now(), case_id, declared_no_involvement=declared,
                                         decision=decision, reasons=reasons, conflict_note=conflict_note))

with t_rely:
    st.markdown("**Reliance actions** (Rule 3 gate)")
    st.caption("Every attempt is evaluated against the gate and logged, whether permitted or blocked.")
    if not ui.can("attempt_reliance"):
        st.caption("Your role can inspect reliance decisions but cannot perform reliance actions.")
    else:
        b1, b2, _ = st.columns([1, 1.4, 1])
        for col, action in zip((b1, b2), R.RELIANCE_ACTIONS):
            if col.button(action, key=f"rely_{action}", width="stretch"):
                ui.flash(S.attempt_reliance(conn, me, ui.now(), case_id, action))
    attempts = S.gate_attempts(conn, case_id)
    ui.table([{"id": a["attempt_id"], "on": ui.short_ts(a["ts"]), "who": f"{S.user_name(conn, a['user'])} ({a['role']})",
               "action": a["action"], "outcome": ui.chip(a["outcome"]), "why": "; ".join(x.lstrip("• ") for x in a["reasons"])}
              for a in attempts],
             [("id", "Attempt"), ("on", "Date"), ("who", "By"), ("action", "Action"), ("outcome", "Outcome"),
              ("why", "Reasons recorded")], raw=("outcome",), nowrap=("id", "on"))

    st.markdown("**Unavailable-evidence exceptions**")
    st.caption("Only after documented reasonable retrieval. Needs reasons, confirmation that duties are met and "
               "separate authorisation by an uninvolved legal lead or external legal reviewer. It never bypasses "
               "an open required inquiry and never marks missing evidence as complete.")
    exs = S.case_exceptions(conn, case_id)
    ui.table([{"id": e["exception_id"], "gap": e["gap"], "impl": e["implications"], "action": e["proposed_action"],
               "by": S.user_name(conn, e["proposed_by"]), "status": ui.chip(e["status"]),
               "auth": f"{S.user_name(conn, e['authoriser'])}, {ui.short_ts(e['authorised_on'])}" if e["authoriser"] else ""}
              for e in exs],
             [("id", "Exception"), ("gap", "Gap"), ("impl", "Implications"), ("action", "Proposed action"),
              ("by", "Proposed by"), ("status", "Status"), ("auth", "Authorised by")], raw=("status",),
             nowrap=("id",))
    gaps = [i for i in items if i["status"] in (R.GAP, R.UNKNOWN) and i["item_type"] in R.SUPPLIER_ITEMS]
    if case["status"] == "active" and gaps:
        with st.expander("Propose an exception"):
            if ui.allowed(R.LEGAL_REVIEWER, action="propose an exception"):
                with st.form("propose"):
                    item = st.selectbox("Evidence gap", [g["item_type"] for g in gaps])
                    impl = st.text_area("Implications of the gap")
                    action = st.text_area("Proposed, action-specific step")
                    reasons = st.text_area("Reasons")
                    duties = st.checkbox("I confirm that applicable duties (reasonable inquiry, disclosure) are met")
                    if st.form_submit_button("Propose exception", type="primary"):
                        ui.flash(S.propose_exception(conn, me, ui.now(), case_id, item_type=item, implications=impl,
                                                     proposed_action=action, reasons=reasons, duties_confirmed=duties))
    pending = [e for e in exs if e["status"] == "Proposed"]
    if pending:
        with st.expander("Authorise an exception", expanded=True):
            if ui.allowed(R.LEGAL_LEAD, R.LEGAL_REVIEWER, action="authorise an exception"):
                with st.form("authorise"):
                    ex_id = st.selectbox("Exception", [e["exception_id"] for e in pending])
                    confirm = st.checkbox("I confirm I have had no prior involvement in this case")
                    if st.form_submit_button("Authorise exception", type="primary"):
                        ui.flash(S.authorise_exception(conn, me, ui.now(), ex_id, confirm))

with t_supply:
    deliveries = S.case_deliveries(conn, case_id)
    ui.table([{"id": d["delivery_id"], "item": d["item_type"], "ref": d["request_ref"],
               "period": R.fmt_range(d["period_start"], d["period_end"]) if d["period_start"] else "—",
               "avail": ui.chip(d["availability"], {"Delivered": "green", "Unavailable": "red"}.get(d["availability"], "violet")),
               "on": ui.short_ts(d["received_on"]), "notes": d["notes"], "sr": d["source_record_id"]}
              for d in deliveries],
             [("id", "Delivery"), ("item", "Item"), ("ref", "Request"), ("period", "Period covered"),
              ("avail", "Response"), ("on", "Received"), ("notes", "Notes"), ("sr", "Source record")],
             raw=("avail",), nowrap=("id", "on", "period"))
    if case["status"] == "active":
        st.markdown("**Record a supplier response**")
        if ui.allowed(R.SUPPLIER_LIAISON, action="record supplier deliveries"):
            with st.form("delivery"):
                a, b, c = st.columns(3)
                item = a.selectbox("Item", R.SUPPLIER_ITEMS)
                ref = b.text_input("Request reference", value=f"ARQ-{case_id}-{len(deliveries) + 1}")
                availability = c.selectbox("Response", [R.DELIVERED, R.UNAVAILABLE, R.UNCONFIRMED])
                a, b = st.columns(2)
                p_start = a.date_input("Period covered from", value=None, format="DD/MM/YYYY")
                p_end = b.date_input("Period covered to", value=None, format="DD/MM/YYYY")
                notes = st.text_input("Notes")
                if st.form_submit_button("Record response and re-run Rule 2", type="primary"):
                    ui.flash(S.record_supplier_delivery(conn, me, ui.now(), case_id=case_id, item_type=item,
                                                        request_ref=ref, period_start=p_start, period_end=p_end,
                                                        availability=availability, notes=notes))
        retrievals = [t for t in open_tasks if t["type"] == "Evidence retrieval"]
        if retrievals:
            st.markdown("**Record retrieval as exhausted** (the gap stays visible)")
            if ui.allowed(R.SUPPLIER_LIAISON, R.LEGAL_LEAD, action="record retrieval as exhausted"):
                with st.form("exhausted"):
                    task_id = st.selectbox("Retrieval request", [t["task_id"] for t in retrievals],
                                           format_func=lambda x: next(f"{x} – {t['title']}" for t in retrievals
                                                                      if t["task_id"] == x))
                    steps = st.text_area("Retrieval steps taken (who was asked, when, and the response)")
                    if st.form_submit_button("Close as unavailable after reasonable retrieval"):
                        ui.flash(S.close_retrieval_unavailable(conn, me, ui.now(), task_id, steps))

with t_expert:
    if case["status"] != "active":
        st.caption("Closed case.")
    elif ui.allowed(R.TECH_REVIEWER, action="record expert statements and run the completeness check"):
        latest = S.latest_statement(conn, case_id)
        defect_ids = [d["defect_id"] for d in S.list_defects(conn)]
        with st.form("statement"):
            st.markdown("**Record an expert statement (new version)**")
            a, b = st.columns(2)
            sid = a.text_input("Statement ID", value=latest["statement_id"] if latest else f"ES-{case_id[1:]}")
            author = b.text_input("Author", value=latest["author"] if latest else "")
            addressed = st.multiselect("PEAKs/KELs the statement addresses", defect_ids,
                                       default=latest["linked_defects"] if latest else [])
            summary = st.text_input("Summary")
            if st.form_submit_button("Record statement"):
                ui.flash(S.record_expert_statement(conn, me, ui.now(), case_id=case_id, statement_id=sid,
                                                   author=author, defects_addressed=addressed, summary=summary))
        if latest:
            st.markdown("**Run the completeness check** against currently linked PEAKs/KELs")
            notes = st.text_input("Check notes", key="check_notes")
            if st.button("Run expert completeness check", type="primary"):
                ui.flash(S.run_expert_check(conn, me, ui.now(), case_id, notes))

with t_help:
    st.caption(f"Helpline and complaint records for branch {case['branch']}: preserves contrary accounts and "
               "recurring patterns.")
    ui.table([{"id": c["complaint_id"], "date": R.fmt_date(c["date"]), "issue": c["issue"], "sr": c["source_record_id"]}
              for c in S.branch_complaints(conn, case["branch"])],
             [("id", "Record"), ("date", "Date"), ("issue", "Issue"), ("sr", "Source record")], nowrap=("id", "date"))

with t_hist:
    st.caption("Full case history from the append-only, hash-chained audit log.")
    log = S.audit_entries(conn, case_id)
    st.dataframe(pd.DataFrame([{"#": e["seq"], "Demo time": e["ts"], "User": e["user"], "Role": e["role"],
                                "Action": e["action"], "Object": e["object"], "Before": e["before"] or "",
                                "After": e["after"] or ""} for e in log]),
                 hide_index=True, height=420)
