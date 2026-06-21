from pathlib import Path

from dotenv import load_dotenv

_pg_root = Path(__file__).resolve().parents[1]
load_dotenv(_pg_root / ".env", override=True)

import streamlit as st
from pages.views import render_chat_panel
from pages.app_bootstrap import render_sidebar, render_page_title, PAGE_INFO

render_sidebar()
render_page_title(PAGE_INFO["P1"], variant="compact")


# =========================
# Views
# =========================
render_chat_panel()
