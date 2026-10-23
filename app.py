from __future__ import annotations

from datetime import date
import pandas as pd
import plotly.express as px
import streamlit as st

from src.synthetic import generate_synthetic_events
from src.engine import validate_events, calculate_attendance, build_timeline

st.set_page_config(page_title="ClassTrace AI v0.1", page_icon="🧭", layout="wide")

st.title("🧭 ClassTrace AI v0.1")
st.caption("Cross-zone student attendance verification · Local software prototype")

st.warning(
    "DEMO MODE: All default records are synthetic and use fictional student IDs. "
    "This is not real school data and must not be used for disciplinary decisions."
)

with st.sidebar:
    st.header("Demo settings")
    n_students = st.slider("Number of fictional students", min_value=5, max_value=40, value=12)
    seed = st.number_input("Random seed", min_value=0, max_value=99999, value=7, step=1)
    inject_faults = st.checkbox("Inject demo faults (missing/duplicate events)", value=True)
    st.markdown("---")
    st.markdown("**Scheduled class**")
    class_start = st.time_input("Class starts", value=pd.Timestamp("10:00").time())
    class_end = st.time_input("Class ends", value=pd.Timestamp("11:00").time())
    st.markdown("---")
    st.caption("No cloud service or paid API is used.")

events, truth = generate_synthetic_events(
    n_students=int(n_students),
    day=date(2026, 10, 22),
    seed=int(seed),
    include_faults=inject_faults,
)

# Keep the source label visible in all reports.
checked = validate_events(events)
attendance = calculate_attendance(
    events,
    class_start=class_start.strftime("%H:%M"),
    class_end=class_end.strftime("%H:%M"),
)

tab_overview, tab_student, tab_events, tab_eval, tab_about = st.tabs(
    ["Overview", "Student timeline", "Event log", "Evaluation", "About & limitations"]
)

with tab_overview:
    st.subheader("Daily overview")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fictional students", attendance["student_id"].nunique() if not attendance.empty else 0)
    c2.metric("Observed events", len(events))
    c3.metric("Events flagged for review", int((checked["status"] == "REVIEW").sum()))
    c4.metric("Mean class attendance", f"{attendance['class_attendance_pct'].mean():.1f}%" if not attendance.empty else "N/A")

    left, right = st.columns(2)
    with left:
        st.markdown("#### Classroom attendance by student")
        if not attendance.empty:
            chart = px.bar(
                attendance, x="student_id", y="class_attendance_pct",
                labels={"student_id": "Fictional student", "class_attendance_pct": "Attendance (%)"},
                range_y=[0, 110], title="Scheduled class window only"
            )
            st.plotly_chart(chart, use_container_width=True)
    with right:
        st.markdown("#### Event status")
        status_counts = checked["status"].value_counts().rename_axis("status").reset_index(name="count")
        chart = px.pie(status_counts, names="status", values="count", title="Rule-based review flags")
        st.plotly_chart(chart, use_container_width=True)

    st.markdown("#### Attendance report")
    st.dataframe(
        attendance.sort_values("student_id"),
        use_container_width=True,
        hide_index=True
    )
    st.download_button(
        "Download attendance report (CSV)",
        data=attendance.to_csv(index=False).encode("utf-8"),
        file_name="classtrace_attendance_report_synthetic.csv",
        mime="text/csv"
    )

with tab_student:
    st.subheader("Student timeline")
    student_ids = sorted(events["student_id"].unique().tolist())
    selected = st.selectbox("Select a fictional student", student_ids)
    student_events = checked[checked["student_id"] == selected].copy().sort_values("timestamp")

    if not student_events.empty:
        plot_df = student_events.dropna(subset=["timestamp"]).copy()
        plot_df["event_label"] = plot_df["zone"] + " · " + plot_df["event_type"]
        fig = px.scatter(
            plot_df, x="timestamp", y="zone", color="event_type",
            hover_data=["event_id", "source", "status", "flags"],
            title=f"Observed event timeline — {selected}"
        )
        fig.update_traces(marker={"size": 12})
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(
            student_events[["timestamp", "zone", "event_type", "source", "status", "flags"]],
            use_container_width=True,
            hide_index=True
        )
        row = attendance[attendance["student_id"] == selected]
        if not row.empty:
            r = row.iloc[0]
            a, b, c = st.columns(3)
            a.metric("Campus paired duration", f"{r['campus_minutes']:.1f} min")
            b.metric("Classroom duration", f"{r['class_minutes']:.1f} min")
            c.metric("Class attendance", f"{r['class_attendance_pct']:.1f}%")
    else:
        st.info("No events for this student.")

with tab_events:
    st.subheader("Observed event log")
    filter_status = st.multiselect("Filter by status", ["OK", "REVIEW"], default=["OK", "REVIEW"])
    filter_zone = st.multiselect("Filter by zone", ["CAMPUS", "CLASS_A"], default=["CAMPUS", "CLASS_A"])
    view = checked[checked["status"].isin(filter_status) & checked["zone"].isin(filter_zone)]
    st.dataframe(view, use_container_width=True, hide_index=True)
    st.download_button(
        "Download observed events (CSV)",
        data=checked.to_csv(index=False).encode("utf-8"),
        file_name="classtrace_observed_events_synthetic.csv",
        mime="text/csv"
    )
    st.caption("A REVIEW flag means the rule engine found a pattern worth checking; it is not proof of misconduct.")

with tab_eval:
    st.subheader("Synthetic-data sanity check")
    st.write(
        "The simulator has a known ground-truth event log. This section compares observed events with that "
        "synthetic truth for an initial engineering sanity check. It does not measure real-world performance."
    )
    truth_keys = set(
        zip(truth["student_id"], truth["zone"], truth["event_type"], pd.to_datetime(truth["timestamp"]).astype(str))
    )
    observed_keys = set(
        zip(events["student_id"], events["zone"], events["event_type"], pd.to_datetime(events["timestamp"]).astype(str))
    )
    exact_match = len(truth_keys & observed_keys)
    recall = exact_match / len(truth_keys) if truth_keys else 0
    st.metric("Exact event recall vs simulator truth", f"{recall * 100:.1f}%")
    st.caption("This simplified exact-match measure is affected by duplicate events and timestamp changes. It is a diagnostic, not a publication-ready metric.")

    st.markdown("#### Review-flag breakdown")
    flagged = checked[checked["status"] == "REVIEW"]
    if flagged.empty:
        st.success("No events were flagged in this particular generated sample.")
    else:
        breakdown = flagged["flags"].value_counts().rename_axis("flag").reset_index(name="count")
        st.dataframe(breakdown, use_container_width=True, hide_index=True)
    st.info(
        "Research next step: create separate train/validation/test scenarios, compare against a rule-only baseline, "
        "and evaluate on independently observer-labelled real event logs before making real-world claims."
    )

with tab_about:
    st.subheader("Scope and limitations")
    st.markdown("""
- **No face recognition in v0.1.** Student IDs are fictional.
- Campus presence and classroom presence are calculated separately.
- Only complete ENTRY→EXIT pairs contribute to durations; unmatched events are not silently filled in.
- Missing-event flags are heuristic. The software cannot always know that an event was missed from the event log alone.
- The default data is synthetic and deterministic for a given random seed.
- Synthetic results must not be described as real-world accuracy.
- Real deployment would require school approval, informed consent where applicable, access control, data minimization, security, and a retention policy.
- Do not use this prototype to automatically punish students or make final attendance decisions.
""")
    st.markdown("**Current version:** v0.1 — rule-based baseline and synthetic data.")

st.markdown("---")
st.caption("ClassTrace AI v0.1 · Runs locally · Synthetic demo data only")
