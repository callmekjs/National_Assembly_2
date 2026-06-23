from __future__ import annotations

from graph.state import QAState

import streamlit as st

def run(state: QAState) -> QAState:
    #st.write ("checkpoint1")
    question = (state.get("question") or "").strip()
    #st.write ("checkpoint2")
    #question = "조태열 장관과 정동영 장관의 대북정책 입장 차이가 뭐야?"
    #st.write ("" + question)
    state["rewritten_query"] = question
    return state
