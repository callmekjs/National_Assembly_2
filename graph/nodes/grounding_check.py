from graph.state import QAState
import re

def run(state: QAState) -> QAState:
    """
    GroundingCheck 단계:
    답변이 실제 근거(보고서 등)에 기반하고 있음을 확인합니다.
    
    1. draft_answer(초안 답변) 내에 "[n]" 인용 번호가 포함되어 있는지 검사합니다.
       - "[1]", "[2]" 등 번호 인용이 있으면 근거를 명시한 것으로 간주함
    2. 검사 결과를 state["grounded"]에 True/False로 저장합니다.

    Args:
        state (QAState): 질의 세션 상태

    Returns:
        QAState: grounded (근거 명시 여부) 플래그가 추가된 상태
    """
    ans = state.get("draft_answer", "")
    state["grounded"] = bool(re.search(r"\[\d+\]", ans))
    print(f"[GroundingCheck] complete (grounded={state['grounded']})")
    
    return state
