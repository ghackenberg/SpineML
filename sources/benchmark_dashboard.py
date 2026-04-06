from __future__ import annotations

import json
import os
from pathlib import Path

if __name__ == "__main__" and os.environ.get("SPINEML_STREAMLIT_BOOTSTRAPPED") != "1":
    os.environ["SPINEML_STREAMLIT_BOOTSTRAPPED"] = "1"
    from streamlit.web.bootstrap import run

    run(str(Path(__file__).resolve()), False, [], {})
    raise SystemExit

import pandas as pd
import streamlit as st

from SpineML.benchmark import (
    CONTROLLER_REGISTRY,
    available_examples,
    order_rows,
    report_rows,
    run_benchmark_suite,
)


st.set_page_config(page_title="SpineML Benchmark Dashboard", layout="wide")
st.title("SpineML Benchmark Dashboard")

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _available_report_files() -> list[str]:
    return sorted(path.name for path in PROJECT_ROOT.glob("*.json"))


def _load_report_frames(report_path: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    report_data = json.loads(report_path.read_text(encoding="utf-8"))
    run_rows = []
    order_rows_data = []

    for run in report_data.get("runs", []):
        run_rows.append({key: value for key, value in run.items() if key != "orders"})
        for order in run.get("orders", []):
            order_rows_data.append(
                {
                    "example_name": run.get("example_name"),
                    "controller_name": run.get("controller_name"),
                    "seed": run.get("seed"),
                    **order,
                }
            )

    return pd.DataFrame(run_rows), pd.DataFrame(order_rows_data), report_data


def _store_report_in_session(report_data: dict, source_label: str) -> None:
    st.session_state["report_data"] = report_data
    st.session_state["report_source_label"] = source_label
    st.session_state["run_df"] = pd.DataFrame(
        [{key: value for key, value in run.items() if key != "orders"} for run in report_data.get("runs", [])]
    )
    order_rows_data = []
    for run in report_data.get("runs", []):
        for order in run.get("orders", []):
            order_rows_data.append(
                {
                    "example_name": run.get("example_name"),
                    "controller_name": run.get("controller_name"),
                    "seed": run.get("seed"),
                    **order,
                }
            )
    st.session_state["order_df"] = pd.DataFrame(order_rows_data)


def _save_report_file(report_data: dict, file_name: str) -> Path:
    file_path = PROJECT_ROOT / file_name
    file_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    return file_path


def _render_report(run_df: pd.DataFrame, order_df: pd.DataFrame, report_data: dict) -> None:
    if run_df.empty:
        st.warning("Der Report enthaelt keine Runs.")
        return

    st.subheader("Uebersicht")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Runs", len(run_df))
    col2.metric("Beispiele", run_df["example_name"].nunique())
    col3.metric("Controller", run_df["controller_name"].nunique())
    col4.metric("Seeds", run_df["seed"].nunique())

    summary_df = (
        run_df.groupby("controller_name", as_index=False)
        .agg(
            avg_total_tardiness=("total_tardiness", "mean"),
            avg_makespan=("final_simulation_time", "mean"),
            avg_machine_utilization=("machine_utilization", "mean"),
            avg_robot_utilization=("robot_utilization", "mean"),
            avg_defective_jobs=("defective_jobs", "mean"),
        )
        .sort_values("avg_total_tardiness")
    )

    st.subheader("Controller-Vergleich")
    st.dataframe(summary_df, use_container_width=True)

    metric_name = st.selectbox(
        "Kennzahl fuer Balkendiagramm",
        options=[
            "total_tardiness",
            "final_simulation_time",
            "machine_utilization",
            "robot_utilization",
            "defective_jobs",
        ],
    )
    chart_df = (
        run_df.groupby(["example_name", "controller_name"], as_index=False)[metric_name]
        .mean()
        .pivot(index="example_name", columns="controller_name", values=metric_name)
    )
    st.bar_chart(chart_df)

    st.subheader("Run-Details")
    st.dataframe(run_df, use_container_width=True)

    st.subheader("Order-Details")
    if order_df.empty:
        st.info("Keine Order-Details im Report vorhanden.")
    else:
        st.dataframe(order_df, use_container_width=True)

    st.subheader("Report JSON")
    default_save_name = st.text_input("Dateiname im Projektordner", value="benchmark-dashboard-report.json")
    if st.button("Report im Projektordner speichern", use_container_width=False):
        saved_path = _save_report_file(report_data, default_save_name)
        st.success(f"Gespeichert: {saved_path.name}")
    st.download_button(
        label="Report herunterladen",
        data=json.dumps(report_data, indent=2),
        file_name="spineml-benchmark-report.json",
        mime="application/json",
    )


with st.sidebar:
    st.header("Konfiguration")
    data_source = st.radio(
        "Datenquelle",
        options=["Vorhandenen Report laden", "Neue Benchmarks starten"],
    )

    if data_source == "Vorhandenen Report laden":
        available_reports = _available_report_files()
        selected_report = st.selectbox(
            "Report-Datei",
            options=available_reports,
            index=0 if available_reports else None,
        )
        run_clicked = st.button("Report anzeigen", use_container_width=True)
        selected_examples = []
        selected_controllers = []
        seed_text = ""
        till_text = ""
    else:
        selected_examples = st.multiselect(
            "Beispiele",
            options=list(available_examples()),
            default=list(available_examples())[:2],
        )
        selected_controllers = st.multiselect(
            "Controller",
            options=sorted(CONTROLLER_REGISTRY.keys()),
            default=["default", "greedy"],
        )
        seed_text = st.text_input("Seeds", value="0,1,2")
        till_text = st.text_input("Simulation till", value="200")
        run_clicked = st.button("Benchmarks starten", use_container_width=True)
        selected_report = None


def _parse_seeds(seed_text_value: str) -> list[int]:
    return [int(part.strip()) for part in seed_text_value.split(",") if part.strip()]


def _parse_till(till_text_value: str) -> float:
    return float(till_text_value) if till_text_value.strip() else float("inf")


if run_clicked:
    if data_source == "Vorhandenen Report laden":
        if selected_report is None:
            st.error("Keine Report-Datei gefunden.")
        else:
            run_df, order_df, report_data = _load_report_frames(PROJECT_ROOT / selected_report)
            _store_report_in_session(report_data, f"Geladen aus: {selected_report}")
    else:
        if not selected_examples:
            st.error("Mindestens ein Beispiel auswählen.")
        elif not selected_controllers:
            st.error("Mindestens einen Controller auswählen.")
        else:
            with st.spinner("Benchmarks laufen..."):
                report = run_benchmark_suite(
                    examples=selected_examples,
                    controllers=selected_controllers,
                    seeds=_parse_seeds(seed_text),
                    till=_parse_till(till_text),
                )
            _store_report_in_session(report.to_dict(), "Neu berechneter Benchmark-Report")

if "report_data" in st.session_state and "run_df" in st.session_state and "order_df" in st.session_state:
    st.caption(st.session_state.get("report_source_label", "Report"))
    _render_report(st.session_state["run_df"], st.session_state["order_df"], st.session_state["report_data"])
else:
    if data_source == "Vorhandenen Report laden":
        st.info("Links eine vorhandene JSON-Report-Datei auswählen und dann anzeigen.")
    else:
        st.info("Links Beispiele, Controller und Seeds waehlen und dann die Benchmarks starten.")
