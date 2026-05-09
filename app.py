from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

# 프로젝트 루트의 `.env`(PG_PORT 등)를 항상 반영 — 셸에 남아 있는 다른 PG_PORT 때문에 덮어쓰게 함.
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

import streamlit as st
from pages.app_bootstrap import render_sidebar
from config.database import init_database

init_database()
render_sidebar()

st.title("국회 회의록 근거 기반 질의응답 (RAG)")
st.markdown(
    """
    ### 메인: LLM으로 답하고, 회의록을 근거로 붙입니다
    - 사이드바 **「회의록 질의」** 에서 질문을 입력하면 **검색 → LLM 답변 → 참고 자료(`[n]`)** 순으로 동작합니다.
    - 답변 생성: `.env`에 **`OPENAI_API_KEY`**가 있으면 **OpenAI**를 우선 사용하고, 없으면 **로컬 LLM**(`service/llm`)을 씁니다. 검색·DB만으로 대화형 답변이 완성되지는 않습니다.

    ### 전제: 데이터 파이프라인
    - 회의록 **수집·Extract·Transform·Load·벡터 적재**는 RAG가 쓸 **검색 데이터**를 만드는 레이어입니다.
    - ETL 실행·복구 절차는 `README`, `OPERATIONS.md`와 사이드바 **「데이터 도구」** 를 참고하세요.
    """
)
