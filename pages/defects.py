import csv
import io

import streamlit as st

import rules as R
import seed
import services as S
import ui

conn = ui.conn()
me = ui.actor()
ui.header("Defect records", "PEAKs and KELs held by the supplier · loaded by file upload")
ui.render_flash()
st.info("**Rule 5 – Reassessment.** Saving a new or updated defect record re-runs Rule 1 against every case, "
        "open and closed, regardless of date. Cases with an earlier decision get a reassessment task that "
        "preserves the original decision and reasoning.", icon=":material/autorenew:")

result = st.session_state.pop("rule5_result", None)
if result:
    st.success(result["message"])
    flagged = [r for r in result["rows"] if r["tasks_created"] != "—" or r["result"] != R.RESULT_LABELS[R.NO_MATCH]]
    ui.table(flagged or result["rows"], [("case_id", "Case"), ("status", "Status"), ("result", "Result"),
                                         ("previous", "Previous"), ("tasks_created", "Tasks created"),
                                         ("explanation", "Explanation")], nowrap=("case_id", "result"))
    with st.expander(f"All {len(result['rows'])} cases screened"):
        ui.table(result["rows"], [("case_id", "Case"), ("status", "Status"), ("result", "Result"),
                                  ("explanation", "Explanation")], nowrap=("case_id", "result"))

counts = {}
for r in conn.execute("SELECT defect_id, result, COUNT(*) n FROM defect_links GROUP BY defect_id, result"):
    counts.setdefault(r["defect_id"], {})[r["result"]] = r["n"]


def scope(value) -> str:
    return value if isinstance(value, str) else ", ".join(value)


rows = []
for d in S.list_defects(conn):
    c = counts.get(d["defect_id"], {})
    flagged = c.get(R.LINKED, 0) + c.get(R.MANUAL_REVIEW, 0)
    rows.append({"id": d["defect_id"], "type": d["type"], "branches": scope(d["affected_branches"]),
                 "period": R.fmt_range(d["affected_start"], d["affected_end"]),
                 "versions": scope(d["versions"]), "symptoms": d["symptoms"],
                 "reported": R.fmt_date(d["date_reported"]), "loaded": ui.short_ts(d["loaded_on"]),
                 "ver": f"v{d['record_version']}",
                 "links": ui.chip(f"{flagged} flagged", "amber") if flagged else ui.chip("0 flagged", "grey")})
ui.table(rows, [("id", "Record"), ("type", "Type"), ("branches", "Affected branches"),
                ("period", "Affected period"), ("versions", "Versions"), ("symptoms", "Symptoms"),
                ("reported", "Reported"), ("loaded", "Loaded"), ("ver", "Version"), ("links", "Case links")],
         raw=("links",), nowrap=("id", "reported", "loaded", "period"))
st.caption("Matching uses the affected period, so a defect reported months later still links to earlier cases. "
           "Each upload is stored verbatim with its source file, receipt time and SHA-256 hash.")

st.subheader("Add or update a defect record")
template = io.StringIO()
writer = csv.DictWriter(template, fieldnames=S.DEFECT_CSV_FIELDS)
writer.writeheader()
writer.writerow(seed.SAMPLE_LATER_DEFECT)

if ui.allowed(R.SUPPLIER_LIAISON, R.TECH_REVIEWER, R.LEGAL_LEAD, action="load defect records"):
    t_demo, t_csv, t_form = st.tabs(["Demo: load the later defect record", "Upload CSV", "Enter manually"])

    def save(records: list[dict], source_file: str) -> None:
        messages, all_rows = [], []
        for rec in records:
            out = S.load_defect(conn, me, ui.now(), rec, source_file=source_file)
            if not out.ok:
                ui.flash(out)
            messages.append(f"{rec['defect_id']}: {out.message}")
            all_rows += out.data["rows"]
        st.session_state["rule5_result"] = {"message": " ".join(messages), "rows": all_rows}
        st.rerun()

    with t_demo:
        d = seed.SAMPLE_LATER_DEFECT
        st.markdown(f"**{d['defect_id']}** — {d['symptoms']}. Branches {d['affected_branches'].replace(';', ', ')}; "
                    f"affected {R.fmt_range(d['affected_start'], d['affected_end'])}; {d['versions']}; reported "
                    f"{R.fmt_date(d['date_reported'])}.")
        if st.button(f"Load {d['defect_id']} and run Rule 5", type="primary",
                     disabled=S.get_defect(conn, d["defect_id"]) is not None):
            save([d], "fujitsu_kel_extract_2013-11-18.csv")
        if S.get_defect(conn, d["defect_id"]):
            st.caption("Already loaded. Use Reset demo data in the sidebar to replay it.")

    with t_csv:
        st.download_button("Download CSV template", template.getvalue(), "defect_template.csv", "text/csv")
        st.caption("Branches and versions are separated by semicolons; use ALL for every branch, Unknown for "
                   "missing values, and Ongoing for an open-ended affected period.")
        upload = st.file_uploader("Defect extract (CSV)", type="csv")
        if upload is not None:
            records, problems = S.parse_defect_csv(upload.getvalue().decode("utf-8-sig"))
            if problems:
                st.error("\n".join(problems))
            else:
                st.write(f"{len(records)} record(s) ready: {', '.join(r['defect_id'] for r in records)}")
                if st.button("Save and run Rule 5", type="primary"):
                    save(records, upload.name)

    with t_form:
        with st.form("defect"):
            a, b, c = st.columns(3)
            defect_id = a.text_input("Record ID (existing ID updates the record)", placeholder="KEL-D08")
            dtype = b.selectbox("Type", ["KEL", "PEAK"])
            branches = c.text_input("Affected branches", placeholder="214;305 or ALL or Unknown")
            a, b, c = st.columns(3)
            start = a.text_input("Affected from (YYYY-MM-DD or Unknown)")
            end = b.text_input("Affected to (YYYY-MM-DD, Ongoing or Unknown)")
            reported = c.text_input("Date reported (YYYY-MM-DD)")
            versions = st.multiselect("Affected Horizon versions", [*R.HORIZON_VERSIONS, "ALL", R.UNKNOWN])
            symptoms = st.text_area("Symptoms")
            if st.form_submit_button("Save and run Rule 5", type="primary"):
                save([dict(defect_id=defect_id, type=dtype, affected_branches=branches, affected_start=start,
                           affected_end=end, versions=";".join(versions) or R.UNKNOWN, symptoms=symptoms,
                           date_reported=reported)], "defect_entry_form")
