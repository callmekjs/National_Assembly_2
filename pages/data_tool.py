from __future__ import annotations
import subprocess
import sys
from datetime import datetime
from pathlib import Path
import streamlit as st
from pages.app_bootstrap import render_sidebar, render_page_title, PAGE_INFO

# =========================
# 공통 페이지 설정
# =========================
st.set_page_config(page_title="국회 회의록 분석기", page_icon="🏛️", layout="wide")
render_sidebar()
render_page_title(PAGE_INFO["PDT"], variant="compact")

# 루트 경로 
APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

def render() -> None:
    st.subheader("ETL 파이프라인")
    _init_state()
    st.markdown("회의록 도메인 기준 기본 ETL 파이프라인을 실행합니다.")
    cols = st.columns(3)
    if cols[0].button("1) Extract", use_container_width=True):
        _run_cmd("Extract", [sys.executable, "-m", "service.etl.extractor.extractor"])
    if cols[1].button("2) Transform", use_container_width=True):
        _run_cmd("Transform", [sys.executable, "-m", "service.etl.transform.pipeline"])
    if cols[2].button("3) Load", use_container_width=True):
        _run_cmd("Load", [sys.executable, "-m", "service.etl.loader.loader_cli", "load", "doc"])
    st.divider()
    _render_logs()


def _init_state() -> None:
    if "etl_logs" not in st.session_state:
        st.session_state.etl_logs = []

def _run_cmd(step: str, cmd: list[str]) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(APP_ROOT))
        st.session_state.etl_logs.append(f"[{ts}] [{step}] return_code={result.returncode}")
        if result.stdout:
            st.session_state.etl_logs.append(result.stdout)
        if result.stderr:
            st.session_state.etl_logs.append(result.stderr)
    except Exception as exc:
        st.session_state.etl_logs.append(f"[{ts}] [{step}] ERROR: {exc}")


def _render_logs() -> None:
    st.subheader("실행 로그")
    if not st.session_state.etl_logs:
        st.info("아직 실행된 작업이 없습니다. 버튼을 눌러 파이프라인을 실행해 보세요.")
        return
    for entry in reversed(st.session_state.etl_logs):
        st.code(entry)


if __name__ == "__main__":
    render()
