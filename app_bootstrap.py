from __future__ import annotations

import streamlit as st

def _hide_builtin_nav():
    """Streamlit 기본 멀티페이지 네비(상단 자동 목록) 숨김 + 사이드바 정돈"""
    st.markdown(
        """
        <style>
          [data-testid="stSidebarNav"] { display: none !important; }
          section[data-testid="stSidebar"] { padding-top: .5rem; }
          /* 사이드바 링크 간격/호버 */
          [data-testid="stSidebar"] a { padding: .35rem .25rem !important; border-radius: 8px; }
          [data-testid="stSidebar"] a:hover { background: rgba(255,255,255,.06); }
        </style>
    """,
        unsafe_allow_html=True,
    )

def _inject_common_styles():
    """페이지 전역에서 재사용할 공통 스타일"""
    st.markdown(
        """
        <style>
          .app-title { font-size: 1.9rem; font-weight: 700; margin: 0 0 .35rem; }
          .app-title--compact { font-size: 36px !important; line-height: 1.3; }
          .stApp { background-color: #ffffff !important; }
          [data-testid="stAppViewContainer"],
          [data-testid="stSidebar"],
          [data-testid="stMarkdownContainer"],
          [data-testid="stHeader"] {
            color: #000000 !important;
          }
          .stApp button {
            color: #000000 !important;
            border: 1px solid #d0d0d0 !important;
            box-shadow: none !important;
            border-radius: 10px !important;
          }
          .stApp button:hover,
          .stApp button:focus {
            background-color: #f5f5f5 !important;
            color: #000000 !important;
            border-color: #b0b0b0 !important;
            box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.05) !important;
          }
          .stApp button:disabled {
            color: rgba(0, 0, 0, 0.4) !important;
            border-color: #d0d0d0 !important;
            box-shadow: none !important;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

def render_sidebar():
    st.set_page_config(
        page_title="국회 회의록 근거 기반 질의응답",
        page_icon="🏛️",
        layout="wide",
    )

    _inject_common_styles()
    _hide_builtin_nav()

    with st.sidebar:
        st.subheader("국회 회의록")
        st.caption("질문하면 회의록 근거와 함께 답합니다.")
