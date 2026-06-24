from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

# 프로젝트 루트의 `.env`(PG_PORT 등)를 항상 반영 — 셸에 남아 있는 다른 PG_PORT 때문에 덮어쓰게 함.
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

import streamlit as st
from app_bootstrap import render_sidebar
from config.database import init_database
from pages.views import render_chat_panel

init_database()
render_sidebar()

st.title("국회 회의록 질의응답")
render_chat_panel()
