import logging

from graph.state import QAState
from graph.utils.level import defaults

logger = logging.getLogger(__name__)

def run(state: QAState) -> QAState:
    """
    기본 검색 메타(top_k, alpha 등)를 깔고, 호출 시 넘긴 meta로 덮어쓴다.
    """
    logger.info("Router start")
    incoming = state.get("meta")
    incoming = incoming if isinstance(incoming, dict) else {}
    state["meta"] = {**defaults(), **incoming}
    logger.info("Router complete → meta=%s", state.get("meta"))
    return state
