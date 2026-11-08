"""Shared Streamlit helpers: sidebar (role switcher, demo clock, reset), styling and widgets."""
from __future__ import annotations

import html
from datetime import date, datetime

import streamlit as st

import db
import rules as R
import seed
import services as S
import access

NAVY = "#16486f"
STAGES = ["Register", "Link defects", "Check coverage", "Investigate", "Review", "Escalate", "Reassess"]

CSS = """
<style>
.block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1440px;}
.cert-header {background: #16486f; color: #fff; padding: 14px 22px; border-radius: 8px; margin-bottom: 12px;
  display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 8px;}
.cert-header .t {font-size: 1.45rem; font-weight: 650; letter-spacing: .01em;}
.cert-header .t .sep {opacity: .55; margin: 0 .45rem;}
.cert-header .s {font-size: .9rem; opacity: .85;}
.chip {display: inline-block; padding: 1px 9px; border-radius: 11px; font-size: .74rem; font-weight: 700;
  letter-spacing: .03em; white-space: nowrap; border: 1px solid;}
.chip.red {background: #fdeaea; color: #8f1d1d; border-color: #f1b4b4;}
.chip.amber {background: #fff3dc; color: #7c4a03; border-color: #f0cf8f;}
.chip.green {background: #e5f4ea; color: #1b5e33; border-color: #a6d4b5;}
.chip.grey {background: #eef1f4; color: #46525e; border-color: #d3dae1;}
.chip.blue {background: #e6eef8; color: #16486f; border-color: #b5c9e2;}
.chip.violet {background: #f1ebfa; color: #55308d; border-color: #d2c0ee;}
table.cert {width: 100%; border-collapse: collapse; font-size: .86rem; margin: 2px 0 14px;}
table.cert th {text-align: left; color: #16486f; background: #f2f6fa; border-bottom: 2px solid #c8d5e2;
  padding: 7px 9px; font-weight: 650; white-space: nowrap;}
table.cert td {border-bottom: 1px solid #e2e7ed; padding: 7px 9px; vertical-align: top; color: #1d2733;}
table.cert td.nowrap {white-space: nowrap;}
table.cert td.wide {min-width: 240px;}
.tbl-wrap {overflow-x: auto; margin-bottom: 14px;}
.tbl-wrap table.cert {margin-bottom: 0;}
table.cert tr:hover td {background: #f8fafc;}
.gate {border-radius: 8px; padding: 13px 18px; margin: 4px 0 16px; border: 1px solid;}
.gate.blocked {background: #fdeeee; border-color: #e7a9a9; color: #6e1414;}
.gate.clear {background: #e9f6ee; border-color: #a3d3b2; color: #14532d;}
.gate.closed {background: #eff2f5; border-color: #d0d7de; color: #39444f;}
.gate .title {font-weight: 750; font-size: 1.06rem; margin-bottom: 3px;}
.gate .lead {font-size: .9rem; margin-bottom: 4px;}
.gate ul {margin: 2px 0 0 1.1rem; padding: 0; font-size: .9rem;}
.gate li {margin: 2px 0;}
.gate .note {font-size: .86rem; margin-top: 6px; opacity: .9;}
.stepper {display: flex; gap: 6px; margin: 4px 0 12px; flex-wrap: wrap;}
.step {flex: 1; min-width: 108px; border: 1px solid #c8d5e2; border-radius: 6px; padding: 5px 9px;
  background: #f6f8fa; color: #6a7886; font-size: .74rem;}
.step b {display: block; color: #6a7886; font-size: .84rem;}
.step.done {background: #e8eff7; color: #34597c;}
.step.done b {color: #16486f;}
.step.current {background: #16486f; border-color: #16486f; color: #dbe6f1;}
.step.current b {color: #fff;}
.step.alert {background: #fff1d6; border-color: #e9b65c; color: #7c4a03;}
.step.alert b {color: #7c4a03;}
.kv {display: flex; gap: 34px; flex-wrap: wrap; margin: 2px 0 10px;}
.kv span {display: block; font-size: .72rem; color: #607080; text-transform: uppercase; letter-spacing: .05em;}
.kv strong {font-size: 1.12rem; color: #14212e; font-weight: 650;}
.quote {border-left: 3px solid #c8d5e2; padding: 4px 12px; color: #34414e; font-size: .9rem; margin: 0 0 12px;}
.muted {color: #607080; font-size: .84rem;}
h3 {color: #16486f;}
</style>
"""

KIND = {
    R.COMPLETE: "green", R.GAP: "amber", R.UNKNOWN: "violet", R.NOT_APPLICABLE: "grey",
    R.BLOCKED: "red", R.CLEAR: "green", R.CLOSED: "grey",
    R.LINKED: "amber", R.MANUAL_REVIEW: "violet", R.NO_MATCH: "grey",
    "Red": "red", "Amber": "amber", "Green": "green",
    "Open": "blue", "Closed": "grey", "Blocked": "red", "Permitted": "green",
    "Proposed": "amber", "Authorised": "green",
    R.ESC_IMMEDIATE: "red", R.ESC_COMMITTEE: "red", R.ESC_LEGAL_LEAD: "amber", R.ESC_NONE: "grey",
    "Unchanged": "green", "ALTERED": "red", "Active": "blue",
}


# --- Session, clock and actor -------------------------------------------------

def get_conn():
    if not db.DEFAULT_DB_PATH.exists():
        with st.spinner("Building the synthetic demo data (first load only)…"):
            seed.ensure(db.DEFAULT_DB_PATH)
    connection = db.connect(db.DEFAULT_DB_PATH)
    S.configure_demo_roles(connection)
    return connection


def conn():
    return st.session_state["conn"]


def today() -> date:
    return st.session_state.get("demo_date", seed.DEMO_DATE)


def now() -> datetime:
    return seed.demo_now(today())


def actor() -> S.Actor:
    return S.get_actor(conn(), st.session_state.get("user_id", "u_tan"))


def sidebar() -> None:
    c = conn()
    users = S.list_users(c)
    with st.sidebar:
        st.markdown(f"<div style='font-size:1.6rem;font-weight:750;color:{NAVY};line-height:1'>CERT</div>"
                    "<div class='muted' style='margin-bottom:10px'>Case Evidence Review Tracker</div>",
                    unsafe_allow_html=True)
        st.markdown("**Acting as**")
        role = st.selectbox("Role", R.ROLES, key="role", label_visibility="collapsed")
        options = [u.user_id for u in users if u.role == role]
        if st.session_state.get("user_id") not in options:
            st.session_state["user_id"] = options[0]
        names = {u.user_id: u.name + (" (external)" if u.is_external else "") for u in users}
        st.selectbox("Named user", options, key="user_id", format_func=names.get)
        st.caption("Your role controls navigation and permitted actions. Investigators see assigned/involved cases; "
                   "other roles have all registered synthetic cases in this demo.")
        st.caption("Role switching stands in for logins; production would need real identity controls.")
        st.markdown("**Demo clock**")
        st.date_input("Demo date", key="demo_date", min_value=date(2013, 1, 1), max_value=date(2014, 12, 31),
                      format="DD/MM/YYYY", label_visibility="collapsed", disabled=role in (R.OVERSEER, R.COMMITTEE))
        st.caption("Working-day escalations use this date. Proposed service standards: deadline within "
                   "5 WD → immediate; 10 WD → legal lead; 20 WD → Committee.")
        with st.popover("Reset demo data (presentation only)", width="stretch", disabled=role in (R.OVERSEER, R.COMMITTEE)):
            st.write("Rebuild the database from the synthetic seed. Every change made in the app is discarded "
                     "and every visitor sees the same starting state.")
            if st.button("Confirm reset", type="primary", disabled=role in (R.OVERSEER, R.COMMITTEE)):
                c.close()
                seed.build(db.DEFAULT_DB_PATH)
                st.session_state["conn"] = get_conn()
                st.session_state["flash"] = ("success", "Demo data reset to the seeded state.", [])
                st.rerun()
        st.caption("All people, branches and records are fictional.")


def init() -> None:
    if st.session_state.get("role") == "Internal audit / Audit & Risk Committee":
        st.session_state["role"] = R.AUDIT
    st.session_state.setdefault("demo_date", seed.DEMO_DATE)
    st.session_state.setdefault("role", R.INVESTIGATOR)
    st.session_state.setdefault("user_id", "u_tan")
    st.session_state["conn"] = get_conn()
    st.html(CSS)


def require_page(name):
    if not access.page_allowed(actor(), name):
        st.warning("Your current role cannot access this page. Select an appropriate demo role in the sidebar.")
        st.stop()


def can(operation):
    return access.allows(actor(), operation)


# --- Feedback -------------------------------------------------------------------

def flash(outcome: S.Outcome) -> None:
    st.session_state["flash"] = ("success" if outcome.ok else "error", outcome.message, outcome.problems)
    st.rerun()


def render_flash() -> None:
    item = st.session_state.pop("flash", None)
    if not item:
        return
    kind, message, problems = item
    body = message + ("".join(f"\n- {p.lstrip('• ')}" for p in problems) if problems else "")
    (st.success if kind == "success" else st.error)(body)
    st.toast(message, icon=":material/check_circle:" if kind == "success" else ":material/block:")


def allowed(*roles: str, action: str = "") -> bool:
    if actor().role in roles:
        return True
    st.caption(f"Switch role to {' or '.join(roles)} to {action}." if action else
               f"Available to: {', '.join(roles)}.")
    return False


# --- Rendering helpers ------------------------------------------------------------

def esc(value) -> str:
    return html.escape("" if value is None else str(value))


def chip(text: str, kind: str | None = None) -> str:
    return f"<span class='chip {kind or KIND.get(text, 'grey')}'>{esc(text)}</span>"


def header(title: str, subtitle: str = "") -> None:
    parts = "<span class='sep'>|</span>".join(esc(p) for p in ["CERT", *title.split(" | ")])
    st.markdown(f"<div class='cert-header'><div class='t'>{parts}</div><div class='s'>{esc(subtitle)}</div></div>",
                unsafe_allow_html=True)


def table(rows: list[dict], columns: list[tuple[str, str]], *, raw: tuple[str, ...] = (),
          nowrap: tuple[str, ...] = (), wide: tuple[str, ...] = ()) -> None:
    """Render rows as a styled HTML table. Columns in `raw` already hold safe HTML."""
    if not rows:
        st.markdown("<div class='muted'>None.</div>", unsafe_allow_html=True)
        return
    head = "".join(f"<th>{esc(label)}</th>" for _, label in columns)
    body = []
    for r in rows:
        cells = []
        for key, _ in columns:
            value = r.get(key, "")
            content = value if key in raw else esc(value)
            cls = " class='nowrap'" if key in nowrap else " class='wide'" if key in wide else ""
            cells.append(f"<td{cls}>{content}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    st.markdown(f"<div class='tbl-wrap'><table class='cert'><thead><tr>{head}</tr></thead>"
                f"<tbody>{''.join(body)}</tbody></table></div>", unsafe_allow_html=True)


def kv(items: list[tuple[str, str]]) -> None:
    inner = "".join(f"<div><span>{esc(k)}</span><strong>{esc(v)}</strong></div>" for k, v in items)
    st.markdown(f"<div class='kv'>{inner}</div>", unsafe_allow_html=True)


def stepper(stage: int, escalated: bool, closed: bool) -> None:
    cells = []
    for i, name in enumerate(STAGES, 1):
        if i == 6:
            cls = "alert" if escalated else ""
            sub = "Active escalation" if escalated else "At any stage"
        elif i == stage:
            cls, sub = "current", "Current stage"
        elif i < stage and i != 6:
            cls, sub = "done", "Done"
        else:
            cls, sub = "", "On new information" if i == 7 else ""
        if closed and i == 5 and stage == 5:
            sub = "Closed"
        cells.append(f"<div class='step {cls}'><b>{i} {name}</b>{esc(sub) or '&nbsp;'}</div>")
    st.markdown(f"<div class='stepper'>{''.join(cells)}</div>", unsafe_allow_html=True)


def gate_banner(gate: R.GateResult) -> None:
    if gate.state == R.BLOCKED:
        title = "Reliance BLOCKED"
        lead = ("A recovery demand, or passing these figures on as reliable, is not permitted because:")
        items = "".join(f"<li>{esc(r)}</li>" for r in gate.reasons)
        body = f"<div class='lead'>{lead}</div><ul>{items}</ul>"
        cls = "blocked"
    elif gate.state == R.CLEAR:
        title, cls = "Reliance CLEAR", "clear"
        body = "<div class='lead'>No open required inquiry, no unexcepted gap, and a current independent review permits reliance.</div>"
    else:
        title, cls = "Case closed", "closed"
        body = "<div class='lead'>No reassessment is open. A new or updated defect record will re-screen this case.</div>"
    notes = "".join(f"<div class='note'>ⓘ {esc(n)}</div>" for n in gate.notes)
    st.markdown(f"<div class='gate {cls}'><div class='title'>{title}</div>{body}{notes}</div>",
                unsafe_allow_html=True)


def money(v) -> str:
    return "—" if v is None else f"£{v:,.0f}"


def short_ts(value: str | None) -> str:
    if not value:
        return ""
    d = datetime.strptime(value[:16], "%Y-%m-%d %H:%M") if len(value) >= 16 else datetime.fromisoformat(value)
    return f"{d.day} {d:%b %Y}"
