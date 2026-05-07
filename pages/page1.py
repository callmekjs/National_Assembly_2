import streamlit as st
from pages.views import render_chat_panel
from pages.app_bootstrap import render_sidebar, render_page_title, PAGE_INFO

# =========================
# 공통 페이지 설정
# =========================
st.set_page_config(
    page_title="국회 회의록 분석기",
    page_icon="🏛️",
    layout="wide",
)

render_sidebar()
render_page_title(PAGE_INFO["P1"], variant="compact")


# =========================
# Views
# =========================
render_chat_panel()
