from __future__ import annotations
import streamlit as st
from pages.app_bootstrap import render_sidebar
from config.database import init_database

st.set_page_config(
    page_title="국회 회의록 분석기",
    page_icon="🏛️",
    layout="wide",
)

init_database()
render_sidebar()

st.title("국회 회의록 분석기")
st.markdown(
    """
    - 이 프로젝트는 회의록 분석용 기본 틀을 중심으로 구성되어 있습니다.
    - 사이드바에서 `회의록 질의` 또는 `데이터 도구` 페이지로 이동해 작업을 진행하세요.
    """
)