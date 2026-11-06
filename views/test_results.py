import streamlit as st

import report_data
import ui

ui.header("Test results", "Saved evaluation of synthetic scenarios")
st.info("These are saved evaluation results, independent of the live demo database. "
        "Synthetic results cannot establish real-world accuracy or reviewer workload.")
if not report_data.REPORT_PATH.exists():
    st.warning("No evaluation report is available. Run python evaluation.py locally and deploy the report.")
    st.stop()

report = report_data.REPORT_PATH.read_text(encoding="utf-8")
sections = report_data.report_sections(report)
metadata = next((line for line in report.splitlines() if line.startswith("Generated ")), "Evaluation date unavailable")
st.caption(metadata)
metrics = report_data.table_rows(sections.get("Effectiveness metrics", ""))
headline = [("Recall", "Relevant links flagged"), ("Gate enforcement", "Prohibited actions blocked"),
            ("Precision", "Flags judged relevant"), ("Permitted actions", "Permitted controls allowed")]
for col, (prefix, label) in zip(st.columns(4), headline):
    row = next((r for r in metrics if r[0].startswith(prefix)), None)
    col.metric(label, row[2] if row and len(row) > 2 else "Not reported")
st.subheader("Nine control scenarios")
scenario_section = next((v for k, v in sections.items() if k.startswith("Table 4.6")), "")
rows = report_data.table_rows(scenario_section)
ui.table([{"scenario": r[1], "expected": r[2], "result": r[4].replace("*", "")}
          for r in rows if len(r) >= 5],
         [("scenario", "Scenario"), ("expected", "Expected control"), ("result", "Recorded result")])
with st.expander("Observed outcomes for each scenario"):
    st.markdown(scenario_section)
for title in ("Effectiveness metrics", "Gate-enforcement battery", "Supporting tests", "Interpretation"):
    with st.expander(title):
        st.markdown(sections.get(title, "Not reported."))
st.download_button("Download saved evaluation", report, file_name="CERT_test_results.md", mime="text/markdown")
st.caption("To refresh: run python evaluation.py locally, review the results, then commit and deploy test_results.md.")
