"""
국회 회의록 RAG — FastAPI 엔드포인트

엔드포인트:
  GET  /health          DB 연결 + 청크 수 확인
  POST /query           질문 → LangGraph 파이프라인 → 답변 + 인용
  GET  /meetings        적재된 회의 목록 (위원회·날짜)
  GET  /logs            최근 쿼리 로그 (모니터링)
  GET  /logs/failures   recall=0 쿼리 목록
  GET  /logs/stats      전체 통계

실행:
  uvicorn api.main:app --reload --port 8000
  Swagger: http://localhost:8000/docs
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import hashlib
import json
import re
import threading

from fastapi import FastAPI, HTTPException
from service.rag.query.question_types import infer_utterance_type as _infer_utype
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

_STREAM_MAX_TOKENS = int(os.getenv("GENERATE_MAX_TOKENS", "1024"))
_CITE_FALLBACK = 5

# ── 쿼리 응답 캐시 (TTL=10분, 최대 200항목) ────────────────────────────
_QUERY_CACHE: dict[str, tuple[dict, float]] = {}
_CACHE_TTL = 600
_CACHE_LOCK = threading.Lock()

# 질문 유형별 적응형 max_tokens
_ADAPTIVE_TOKENS: dict[str, int] = {
    "unanswerable": 300,
    "speaker_statement": 700,
    "date_based": 700,
    "numerical_fact": 650,
    "quote_exact": 700,
    "speaker_confusion": 650,
    "policy_summary": 900,
    "comparison": 900,
    "multi_chunk": 900,
    "cause_effect": 800,
    "aggregation": 800,
    "cross_committee": 900,
}


def _query_cache_key(question: str, committee: str, top_k: int) -> str:
    raw = f"{question.strip()}|{committee or ''}|{top_k}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _query_cache_get(key: str) -> dict | None:
    with _CACHE_LOCK:
        entry = _QUERY_CACHE.get(key)
        if entry is None:
            return None
        payload, ts = entry
        if time.time() - ts > _CACHE_TTL:
            del _QUERY_CACHE[key]
            return None
        return payload


def _query_cache_set(key: str, payload: dict) -> None:
    with _CACHE_LOCK:
        _QUERY_CACHE[key] = (payload, time.time())
        if len(_QUERY_CACHE) > 200:
            oldest = sorted(_QUERY_CACHE.items(), key=lambda x: x[1][1])[:50]
            for k, _ in oldest:
                del _QUERY_CACHE[k]

app = FastAPI(
    title="국회 회의록 RAG API",
    description="외교통일위원회 회의록 기반 근거 인용 질의응답",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 스키마 ───────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=500, description="질문")
    committee: Optional[str] = Field(None, description="위원회 필터 (미지정 시 전체 위원회 검색)")
    top_k: int = Field(5, ge=1, le=20, description="검색 청크 수")
    use_fusion: bool = Field(True, description="Fusion 검색(BM25+벡터 RRF) 활성화")
    use_neural_reranker: bool = Field(True, description="Neural Reranker 활성화")
    history: Optional[list[dict]] = Field(None, description="멀티턴 대화 히스토리 [{role, content}]")


class Citation(BaseModel):
    index: int
    speaker: Optional[str] = None
    date: Optional[str] = None
    committee: Optional[str] = None
    content_preview: Optional[str] = None
    pdf_url: Optional[str] = None
    pdf_download_url: Optional[str] = None
    page: Optional[int] = None
    search_text: Optional[str] = None


class QueryResponse(BaseModel):
    answer: str
    grounding_level: str
    doc_count: int
    citations: list[Citation]
    latency_total_ms: float
    latency_retrieve_ms: Optional[float] = None
    latency_generate_ms: Optional[float] = None


class MeetingItem(BaseModel):
    source_id: str
    committee: str
    meeting_date: str
    doc_count: int
    source_path: Optional[str] = None
    meeting_session: Optional[str] = None
    meeting_round: Optional[str] = None
    meeting_label: Optional[str] = None


# ── 의존성: DB 연결 ─────────────────────────────────────────────────

def _db_conn():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", "5433")),
        database=os.getenv("PG_DB", "skn_project"),
        user=os.getenv("PG_USER", "postgres"),
        password=os.getenv("PG_PASSWORD", "post1234"),
    )


def _meeting_scope(meeting_key: str) -> tuple[str, tuple[str]]:
    """회의 상세 조회 범위. source_id를 우선 사용하고 날짜 호출도 기존 호환으로 허용."""
    key = (meeting_key or "").strip()
    if "_" in key:
        return "source_id = %s", (key,)
    return "metadata->>'meeting_date' = %s", (key,)


def _lookup_pdf_path(source_id: str) -> Path | None:
    """source_id로 chunks_v2 metadata의 source_path를 찾아 로컬 PDF 경로를 반환."""
    source_id = (source_id or "").strip()
    if not source_id:
        return None
    try:
        with _db_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT metadata->>'source_path'
                FROM chunks_v2
                WHERE source_id = %s
                  AND metadata->>'source_path' IS NOT NULL
                  AND metadata->>'source_path' <> ''
                LIMIT 1
                """,
                (source_id,),
            )
            row = cur.fetchone()
        if row and row[0]:
            candidate = ROOT / str(row[0]).replace("\\", "/")
            if candidate.is_file():
                return candidate
    except Exception:
        pass
    for candidate in ROOT.glob(f"incoming_data/**/{source_id}.pdf"):
        if candidate.is_file():
            return candidate
    return None


def _meeting_number_info(source_id: str) -> dict[str, Optional[str]]:
    """추출된 첫 페이지에서 '제434회 제1차 회의' 표시값을 만든다."""
    source_id = (source_id or "").strip()
    if not source_id:
        return {"meeting_session": None, "meeting_round": None, "meeting_label": None}

    pages_path = ROOT / "data" / "v2" / "extract" / source_id / "pages.jsonl"
    raw_text = ""
    try:
        with pages_path.open("r", encoding="utf-8") as f:
            first = json.loads(f.readline() or "{}")
        raw_text = str(first.get("raw_text") or "")
    except Exception:
        raw_text = ""

    head = raw_text[:1200]
    first_line = head.splitlines()[0] if head else ""
    search_text = first_line or head

    session_match = re.search(r"제\s*(\d+)\s*회", search_text)
    round_match = re.search(r"제\s*(\d+)\s*차", search_text)
    if not round_match and search_text != head:
        round_match = re.search(r"제\s*(\d+)\s*차", head)

    meeting_session = session_match.group(1) if session_match else None
    meeting_round = round_match.group(1) if round_match else None

    if meeting_session and meeting_round:
        label = f"제{meeting_session}회 제{meeting_round}차 회의"
    elif meeting_session:
        label = f"제{meeting_session}회 회의"
    elif meeting_round:
        label = f"제{meeting_round}차 회의"
    else:
        label = None

    return {
        "meeting_session": meeting_session,
        "meeting_round": meeting_round,
        "meeting_label": label,
    }


def _build_citation(index: int, cit: dict) -> Citation:
    preview = (cit.get("quote") or cit.get("chunk_text") or "")[:120]
    _raw_search = (cit.get("quote") or cit.get("chunk_text") or preview or "").strip()
    # Chrome #search= 는 짧고 고유한 구절일수록 정확히 매칭됨
    search_text = _raw_search[10:90].strip() if len(_raw_search) > 90 else _raw_search
    source_id = str(cit.get("source_id") or "").strip()
    source_path = str(cit.get("source_path") or "").strip()
    page_raw = cit.get("page_no")
    page = int(page_raw) if page_raw is not None else None
    pdf_url = None
    pdf_download_url = None
    if source_id and source_path and _lookup_pdf_path(source_id):
        pdf_url = f"/pdfs/{source_id}"
        pdf_download_url = f"/pdfs/{source_id}/download"
    return Citation(
        index=index,
        speaker=cit.get("speaker") or None,
        date=cit.get("date") or None,
        committee=cit.get("committee") or None,
        content_preview=preview or None,
        pdf_url=pdf_url,
        pdf_download_url=pdf_download_url,
        page=page,
        search_text=search_text or None,
    )


# ── 앱 기동 시 초기화 ───────────────────────────────────────────────

@app.on_event("startup")
def startup():
    try:
        from service.monitoring.query_logger import setup_table
        setup_table()
        print("[api] query_logs 테이블 준비 완료")
    except Exception as e:
        print(f"[api] query_logs 초기화 실패 (계속 진행): {e}")


# ── 엔드포인트 ──────────────────────────────────────────────────────

@app.get("/health", summary="헬스 체크")
def health():
    """DB 연결 상태와 v2 청크·임베딩 수를 반환합니다."""
    try:
        with _db_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM chunks_v2")
            chunk_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM embeddings_e5_v2")
            embed_count = cur.fetchone()[0]
        return {
            "status": "ok",
            "db": "ok",
            "schema": "v2",
            "chunks": chunk_count,
            "embeddings": embed_count,
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB 연결 실패: {e}")


@app.post("/query", response_model=QueryResponse, summary="회의록 질의응답")
def query(req: QueryRequest):
    """
    질문을 받아 LangGraph RAG 파이프라인을 실행하고 답변과 출처를 반환합니다.

    - **grounding_level**: FULL / PARTIAL / NONE
    - **citations**: 답변에 사용된 회의록 청크 목록
    - **latency_*_ms**: 각 단계 처리 시간(ms)
    """
    t_start = time.perf_counter()

    try:
        from graph.app_graph import build_app
        graph = build_app()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파이프라인 초기화 실패: {e}")

    meta = {
        "top_k": req.top_k,
        "rerank_n": min(req.top_k, 5),
        "committee": req.committee or None,
        "use_fusion": req.use_fusion,
        "use_neural_reranker": req.use_neural_reranker,
        "use_v2_retrieval": True,
    }

    t_retrieve_start: Optional[float] = None
    t_retrieve_end: Optional[float] = None
    t_generate_start: Optional[float] = None
    t_generate_end: Optional[float] = None

    try:
        t_retrieve_start = time.perf_counter()
        result = graph.invoke({"question": req.question, "meta": meta})
        t_end = time.perf_counter()

        # latency_ms가 state에 기록된 경우 활용
        latency_info: dict = result.get("latency_ms") or {}
        t_retrieve_ms = latency_info.get("retrieve_ms") or None
        t_generate_ms = latency_info.get("generate_ms") or None

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파이프라인 오류: {e}")

    t_total_ms = (t_end - t_start) * 1000

    answer = result.get("draft_answer") or ""
    grounding_level = result.get("grounding_level") or "NONE"
    docs = result.get("reranked") or result.get("retrieved") or []
    raw_citations = result.get("citations") or []

    # 답변에서 실제 사용된 [n] 번호만 추출 → 그것만 노출, 없으면 top 5
    _used_nums = set(int(m.group(1)) for m in re.finditer(r'\[(\d+)\]', answer))

    def _build_cit_dict(doc: dict) -> dict:
        meta_doc = doc.get("metadata") or {}
        preview = (doc.get("chunk_text") or doc.get("content") or "")[:120]
        return {
            "source_id": doc.get("source_id", ""),
            "date": meta_doc.get("meeting_date") or doc.get("date"),
            "speaker": doc.get("speaker"),
            "committee": meta_doc.get("committee"),
            "quote": preview,
            "chunk_text": doc.get("chunk_text") or doc.get("content") or "",
            "source_path": meta_doc.get("source_path") or "",
            "page_no": meta_doc.get("page_no"),
        }

    citations: list[Citation] = []
    if raw_citations:
        src = raw_citations[:10]
        for i, cit in enumerate(src, start=1):
            if i in _used_nums:
                citations.append(_build_citation(i, cit))
        if not citations:
            citations = [_build_citation(i, cit) for i, cit in enumerate(src[:_CITE_FALLBACK], start=1)]
    else:
        src_docs = docs[:10]
        for i, doc in enumerate(src_docs, start=1):
            if i in _used_nums:
                citations.append(_build_citation(i, _build_cit_dict(doc)))
        if not citations:
            citations = [_build_citation(i, _build_cit_dict(doc)) for i, doc in enumerate(src_docs[:_CITE_FALLBACK], start=1)]

    # 쿼리 로그 저장 (비동기 없이 동기 처리 — 실패해도 응답에 영향 없음)
    try:
        from service.monitoring.query_logger import log_query
        log_query(
            question=req.question,
            answer=answer,
            grounding_level=grounding_level,
            doc_count=len(docs),
            committee=req.committee,
            latency_total_ms=round(t_total_ms, 1),
            latency_retrieve_ms=round(t_retrieve_ms, 1) if t_retrieve_ms else None,
            latency_generate_ms=round(t_generate_ms, 1) if t_generate_ms else None,
        )
    except Exception:
        pass

    return QueryResponse(
        answer=answer,
        grounding_level=grounding_level,
        doc_count=len(docs),
        citations=citations,
        latency_total_ms=round(t_total_ms, 1),
        latency_retrieve_ms=round(t_retrieve_ms, 1) if t_retrieve_ms else None,
        latency_generate_ms=round(t_generate_ms, 1) if t_generate_ms else None,
    )


def _extract_claim_text(answer: str, num: int, max_len: int = 70) -> str | None:
    """답변에서 [n] 직전 주장 문구를 추출해 viewer search_text로 활용.
    chunk quote 대신 LLM이 실제 인용한 맥락으로 PDF 하이라이트 → 내용 불일치 방지.

    [^\n\[] 로 '[' 문자를 차단해 [1]이 여러 번 나올 때 다음 [1]까지 탐욕 매칭되는
    버그를 방지한다.
    """
    m = re.search(rf'([가-힣a-zA-Z][^\n\[]{10,120})\[{num}\]', answer)
    if not m:
        return None
    claim = re.sub(r'\*\*', '', m.group(1)).strip()
    return claim[-max_len:] if len(claim) > max_len else claim


def _citations_from_result(result: dict) -> list[Citation]:
    docs = result.get("reranked") or result.get("retrieved") or []
    raw_citations = result.get("citations") or []
    out: list[Citation] = []
    if raw_citations:
        for i, cit in enumerate(raw_citations[:10], start=1):
            out.append(_build_citation(i, cit))
    else:
        for i, doc in enumerate(docs[:10], start=1):
            meta_doc = doc.get("metadata") or {}
            preview = (doc.get("chunk_text") or doc.get("content") or "")[:120]
            out.append(_build_citation(i, {
                "source_id": doc.get("source_id", ""),
                "date": meta_doc.get("meeting_date") or doc.get("date"),
                "speaker": doc.get("speaker"),
                "committee": meta_doc.get("committee"),
                "quote": preview,
                "chunk_text": doc.get("chunk_text") or doc.get("content") or "",
                "source_path": meta_doc.get("source_path") or "",
                "page_no": meta_doc.get("page_no"),
            }))
    return out


@app.post("/query/stream", summary="회의록 질의응답 (스트리밍)")
def query_stream(req: QueryRequest):
    """SSE 스트리밍: 첫 토큰을 빠르게 전달하고 답변을 점진적으로 렌더링합니다."""

    def event_stream():
        t_start = time.perf_counter()
        try:
            from graph.nodes import router, query_rewrite, retrieve_pg, rerank, context_trim, grounding_check, guardrail
            from service.llm.llm_client import _stream_openai
            from service.llm.prompt_templates import build_system_prompt, build_user_prompt, needs_reasoning_model
            from datetime import date

            # 캐시 확인 (히스토리 없는 단발성 질문만 캐시)
            _use_cache = not req.history
            _cache_key = _query_cache_key(req.question, req.committee or "", req.top_k)
            if _use_cache:
                cached = _query_cache_get(_cache_key)
                if cached:
                    cached_payload = {**cached, "latency": 0, "cached": True}
                    yield f"data: {json.dumps(cached_payload, ensure_ascii=False)}\n\n"
                    return

            meta = {
                "top_k": min(req.top_k, 4),
                "rerank_n": min(req.top_k, 4),
                "committee": req.committee or None,
                "use_fusion": req.use_fusion,
                "use_neural_reranker": True,
                "use_v2_retrieval": True,
            }
            state: dict = {"question": req.question, "meta": meta}

            # 파이프라인: 검색 → context 구성
            state = router.run(state)
            state = query_rewrite.run(state)
            state = retrieve_pg.run(state)
            state = rerank.run(state)
            state = context_trim.run(state)

            # 존재 여부 질문: 전제 검증 먼저 — 없으면 스트리밍 스킵
            from graph.nodes.generate import _verify_claim, _REFUSAL_ANSWER, _is_existence_query
            if _is_existence_query(req.question):
                _ctx = state.get("context", "")
                if not _verify_claim(req.question, _ctx):
                    t_total_ms = round((time.perf_counter() - t_start) * 1000, 1)
                    yield f"data: {json.dumps({'type': 'done', 'answer': _REFUSAL_ANSWER, 'grounding': 'REFUSED', 'citations': [], 'latency': t_total_ms}, ensure_ascii=False)}\n\n"
                    return

            # LLM 스트리밍
            system_prompt = build_system_prompt(
                state.get("question", ""),
                committee=(state.get("meta") or {}).get("committee", ""),
                question_type=(state.get("meta") or {}).get("question_type", ""),
            )
            _committee = (state.get("meta") or {}).get("committee", "")
            user_prompt = build_user_prompt(
                state.get("question", ""),
                state.get("context", ""),
                reference_date=date.today(),
                doc_name_query=bool((state.get("meta") or {}).get("doc_name_query")),
                question_type=(state.get("meta") or {}).get("question_type", ""),
                committee=_committee,
            )

            _reasoning = needs_reasoning_model(req.question, committee=_committee)
            _gen_model = os.getenv("OPENAI_REASONING_MODEL", "gpt-4o") if _reasoning else None

            # 질문 유형에 따른 적응형 max_tokens
            _qtype = (state.get("meta") or {}).get("question_type", "")
            _max_tokens = min(_STREAM_MAX_TOKENS, _ADAPTIVE_TOKENS.get(_qtype, 800))

            # 멀티턴 히스토리 (최근 6개 메시지 = 3턴)
            _history = (req.history or [])[-6:] or None

            tokens: list[str] = []
            for token in _stream_openai(system_prompt, user_prompt, max_tokens=_max_tokens, model=_gen_model, history=_history):
                tokens.append(token)
                yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"

            draft_answer = "".join(tokens)
            state["draft_answer"] = draft_answer

            # Grounding check + guardrail (토큰 수집 후)
            state = grounding_check.run(state)
            state = guardrail.run(state)

            final_answer = state.get("draft_answer", "")

            # 사용된 [n] 번호를 첫 등장 순서대로 [1][2]... 재번호
            used_nums = list(dict.fromkeys(
                int(m.group(1)) for m in re.finditer(r'\[(\d+)\]', final_answer)
            ))
            if used_nums:
                remap = {orig: new for new, orig in enumerate(used_nums, start=1)}
                final_answer = re.sub(
                    r'\[(\d+)\]',
                    lambda m: f"[{remap.get(int(m.group(1)), int(m.group(1)))}]",
                    final_answer,
                )

            citations = _citations_from_result(state)
            if state.get("grounding_level") == "REFUSED":
                citations = []  # 올바른 거절 답변 — 참고자료 노출 안 함
            elif used_nums:
                cite_map = {c.index: c for c in citations}
                renumbered = []
                for orig, new in remap.items():
                    if orig in cite_map:
                        d = cite_map[orig].model_dump()
                        d["index"] = new
                        claim = _extract_claim_text(final_answer, new)
                        if claim:
                            d["search_text"] = claim
                        renumbered.append(Citation(**d))
                citations = sorted(renumbered, key=lambda c: c.index) or citations[:_CITE_FALLBACK]
            else:
                citations = citations[:_CITE_FALLBACK]

            t_total_ms = round((time.perf_counter() - t_start) * 1000, 1)

            done_payload = {
                "type": "done",
                "answer": final_answer,
                "grounding": state.get("grounding_level", "NONE"),
                "citations": [c.model_dump() for c in citations],
                "latency": t_total_ms,
            }
            # 정상 답변만 캐시 (히스토리 없는 요청, REFUSED 제외)
            if _use_cache and state.get("grounding_level") != "REFUSED":
                _query_cache_set(_cache_key, done_payload)
            yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/pdfs/{source_id}", summary="회의록 PDF 원문 보기")
def get_pdf(source_id: str):
    """source_id에 해당하는 회의록 PDF 파일을 브라우저 viewer에서 열 수 있게 반환합니다."""
    path = _lookup_pdf_path(source_id)
    if not path:
        raise HTTPException(status_code=404, detail="PDF 파일을 찾을 수 없습니다.")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=path.name,
        content_disposition_type="inline",
    )


@app.get("/pdfs/{source_id}/download", summary="회의록 PDF 다운로드")
def download_pdf(source_id: str):
    """source_id에 해당하는 회의록 PDF 파일을 다운로드합니다."""
    path = _lookup_pdf_path(source_id)
    if not path:
        raise HTTPException(status_code=404, detail="PDF 파일을 찾을 수 없습니다.")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=path.name,
        content_disposition_type="attachment",
    )


@app.get("/pdfs/{source_id}/viewer", summary="회의록 PDF 뷰어 (PDF.js + 하이라이트)", response_class=HTMLResponse)
def pdf_viewer(source_id: str, page: int = 1, search: str = ""):
    """PDF.js 기반 커스텀 뷰어 — 인용 텍스트를 노란색으로 하이라이트합니다."""
    if not _lookup_pdf_path(source_id):
        raise HTTPException(status_code=404, detail="PDF 파일을 찾을 수 없습니다.")

    pdf_url_js = json.dumps(f"/pdfs/{source_id}")
    init_page_js = json.dumps(page)
    search_js = json.dumps(search)

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>회의록 원문</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ background: #525659; font-family: 'Noto Sans KR', sans-serif; min-height: 100vh; }}

    #toolbar {{
      background: #1a1a2e;
      color: #e0e0e0;
      padding: 8px 14px;
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      position: sticky;
      top: 0;
      z-index: 100;
      box-shadow: 0 2px 6px rgba(0,0,0,0.5);
    }}
    .tb-btn {{
      background: #2d4a8a;
      border: none;
      color: #fff;
      padding: 4px 11px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 12px;
    }}
    .tb-btn:hover:not(:disabled) {{ background: #3a5ca8; }}
    .tb-btn:disabled {{ opacity: 0.35; cursor: default; }}
    #page-info {{ flex: 1; text-align: center; }}
    #search-badge {{
      background: rgba(255,220,0,0.15);
      color: #ffd700;
      border: 1px solid rgba(255,220,0,0.35);
      padding: 2px 8px;
      border-radius: 10px;
      font-size: 11px;
      display: none;
      max-width: 200px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}

    #viewer {{
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 18px 12px;
    }}
    .page-wrap {{
      position: relative;
      box-shadow: 0 4px 16px rgba(0,0,0,0.55);
      background: #fff;
    }}
    canvas {{ display: block; }}

    #msg {{
      color: #ccc;
      padding: 40px 20px;
      text-align: center;
      font-size: 14px;
    }}
  </style>
</head>
<body>
  <div id="toolbar">
    <button class="tb-btn" id="btn-prev">◀ 이전</button>
    <span id="page-info">로딩 중…</span>
    <button class="tb-btn" id="btn-next">다음 ▶</button>
    <span id="search-badge"></span>
  </div>
  <div id="viewer"><div id="msg">PDF 로딩 중…</div></div>

  <script>
    const PDF_URL   = {pdf_url_js};
    const INIT_PAGE = {init_page_js};
    const SEARCH    = {search_js};

    let pdf = null, cur = INIT_PAGE, total = 0;
    const viewer  = document.getElementById('viewer');
    const msg     = document.getElementById('msg');
    const pgInfo  = document.getElementById('page-info');
    const badge   = document.getElementById('search-badge');
    const btnPrev = document.getElementById('btn-prev');
    const btnNext = document.getElementById('btn-next');

    btnPrev.onclick = () => {{ if (cur > 1)     goto(cur - 1); }};
    btnNext.onclick = () => {{ if (cur < total) goto(cur + 1); }};

    /* ── PDF.js 로드 ── */
    const s = document.createElement('script');
    s.src = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js';
    s.onload = init;
    s.onerror = () => {{
      const s2 = document.createElement('script');
      s2.src = 'https://unpkg.com/pdfjs-dist@3.11.174/build/pdf.min.js';
      s2.onload = init;
      s2.onerror = () => {{ msg.textContent = 'PDF.js 로드 실패 (네트워크 확인)'; }};
      document.head.appendChild(s2);
    }};
    document.head.appendChild(s);

    async function init() {{
      pdfjsLib.GlobalWorkerOptions.workerSrc =
        'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
      try {{
        pdf = await pdfjsLib.getDocument(PDF_URL).promise;
        total = pdf.numPages;
        cur   = Math.max(1, Math.min(INIT_PAGE, total));
        msg.style.display = 'none';
        await render(cur);
      }} catch(e) {{
        msg.textContent = 'PDF 로드 오류: ' + e.message;
      }}
    }}

    async function goto(n) {{
      cur = n;
      await render(n);
    }}

    async function render(n) {{
      viewer.innerHTML = '';
      btnPrev.disabled = n <= 1;
      btnNext.disabled = n >= total;
      pgInfo.textContent = n + ' / ' + total + ' 페이지';

      const page = await pdf.getPage(n);
      const avail = Math.min(window.innerWidth - 24, 960);
      const scale = avail / page.getViewport({{scale: 1}}).width;
      const vp    = page.getViewport({{scale}});

      const wrap = document.createElement('div');
      wrap.className = 'page-wrap';
      wrap.style.width  = vp.width  + 'px';
      wrap.style.height = vp.height + 'px';

      const canvas = document.createElement('canvas');
      canvas.width  = vp.width;
      canvas.height = vp.height;
      await page.render({{canvasContext: canvas.getContext('2d'), viewport: vp}}).promise;
      wrap.appendChild(canvas);

      if (SEARCH) {{
        const hits = await highlight(page, canvas, vp, SEARCH, scale);
        if (hits > 0) {{
          badge.style.display = 'inline';
          badge.textContent   = '하이라이트: ' + SEARCH.slice(0, 25) + (SEARCH.length > 25 ? '…' : '');
        }}
      }}

      viewer.appendChild(wrap);
    }}

    /* ── 텍스트 하이라이트 ── */
    /* 발언자 표시 줄 판별: ○홍길동, ◯장관 등 — 이름·직함만 있는 짧은 아이템 */
    function isSpeakerLabel(str) {{
      return /^[○◯]\s*[가-힣]/.test(str.trim());
    }}

    async function highlight(page, canvas, vp, search, scale) {{
      const tc  = await page.getTextContent();
      const ctx = canvas.getContext('2d');

      /* 전처리: 공백 제거한 연결 문자열 + 각 아이템의 위치 (발언자 줄 제외) */
      const norm  = s => s.replace(/\\s+/g, '').toLowerCase();
      const needle = norm(search.slice(0, 60));
      if (!needle) return 0;

      let concat = '';
      const spans = [];
      for (const item of tc.items) {{
        if (!item.str) continue;
        /* 발언자 이름 줄(○장관 조태열 등)은 하이라이트 대상에서 제외 */
        if (isSpeakerLabel(item.str)) continue;
        const n = norm(item.str);
        spans.push({{ s: concat.length, e: concat.length + n.length, item }});
        concat += n;
      }}

      /* 문자열 검색 */
      const idx = concat.indexOf(needle.slice(0, Math.min(20, needle.length)));
      let count = 0;

      ctx.save();
      ctx.fillStyle = 'rgba(255, 215, 0, 0.45)';

      if (idx !== -1) {{
        const end = idx + needle.length;
        for (const sp of spans) {{
          if (sp.e <= idx || sp.s >= end) continue;
          drawItem(ctx, sp.item, vp, scale);
          count++;
        }}
      }}

      /* fallback: 단어 단위 매칭 (발언자 줄 제외) */
      if (count === 0) {{
        const words = search.split(/\\s+/).filter(w => w.length > 2);
        for (const sp of spans) {{
          const t = sp.item.str.toLowerCase();
          if (words.some(w => t.includes(w.toLowerCase()))) {{
            drawItem(ctx, sp.item, vp, scale);
            count++;
          }}
        }}
      }}

      ctx.restore();
      return count;
    }}

    function drawItem(ctx, item, vp, scale) {{
      const tx = pdfjsLib.Util.transform(vp.transform, item.transform);
      const h = Math.hypot(tx[2], tx[3]);   /* font height in canvas px */
      /* item.width is in PDF user-space units (pt); multiply by viewport scale */
      const w = Math.max(item.width * scale, h * 0.4);
      ctx.fillRect(tx[4], tx[5] - h * 1.0, w, h * 1.15);
    }}
  </script>
</body>
</html>"""
    return HTMLResponse(content=html, headers={"Cache-Control": "no-store"})


@app.get("/meetings", response_model=list[MeetingItem], summary="회의 목록 조회")
def meetings():
    """적재된 회의록의 PDF 단위 회의 목록과 청크 수를 반환합니다."""
    sql = """
    SELECT
        source_id,
        COALESCE(MIN(metadata->>'committee'), '알 수 없음') AS committee,
        MIN(metadata->>'meeting_date') AS meeting_date,
        MIN(metadata->>'source_path')  AS source_path,
        COUNT(*)                  AS doc_count
    FROM chunks_v2
    WHERE section_type = 'body'
      AND source_id IS NOT NULL
      AND source_id <> ''
      AND metadata->>'committee' IS NOT NULL
      AND metadata->>'meeting_date' IS NOT NULL
    GROUP BY source_id
    ORDER BY meeting_date DESC, source_id DESC
    LIMIT 500
    """
    try:
        import psycopg2.extras
        with _db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        items: list[MeetingItem] = []
        for row in rows:
            payload = dict(row)
            payload.update(_meeting_number_info(str(payload.get("source_id") or "")))
            items.append(MeetingItem(**payload))
        return items
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB 오류: {e}")


@app.get("/logs", summary="최근 쿼리 로그")
def logs(limit: int = 50):
    """최근 쿼리 로그를 반환합니다."""
    from service.monitoring.query_logger import get_recent_logs
    return get_recent_logs(limit=limit)


@app.get("/logs/failures", summary="검색 실패 쿼리 (recall=0)")
def log_failures(limit: int = 20):
    """검색 결과가 0건이었던 쿼리 목록을 반환합니다."""
    from service.monitoring.query_logger import get_recent_failures
    return get_recent_failures(limit=limit)


@app.get("/logs/stats", summary="쿼리 통계")
def log_stats():
    """전체 쿼리 통계 (총 건수, recall=0 비율, 평균 latency, grounding 분포)를 반환합니다."""
    from service.monitoring.query_logger import get_stats
    return get_stats()


# ── 회의 탐색 ────────────────────────────────────────────────────────

_ISSUE_TAG_KEYWORDS: dict[str, list[str]] = {
    "대북전단": ["대북전단", "전단지", "삐라"],
    "오물풍선": ["오물풍선", "오물 풍선"],
    "북핵·비핵화": ["북핵", "비핵화", "핵무기", "ICBM", "탄도미사일"],
    "한미동맹": ["한미동맹", "방위비", "주한미군"],
    "재외국민": ["재외국민", "교민", "해외동포"],
    "남북대화": ["남북대화", "남북 관계", "남북교류"],
    "트럼프·관세": ["트럼프", "관세"],
    "북한인권": ["북한 인권", "북한인권"],
    "대북제재": ["대북제재", "유엔 제재", "UN 제재"],
    "통일정책": ["통일정책", "통일 정책"],
}


def _extract_issue_tags(texts: list[str]) -> list[str]:
    combined = " ".join(texts)
    return [tag for tag, keywords in _ISSUE_TAG_KEYWORDS.items()
            if any(kw in combined for kw in keywords)]


class SpeakerStat(BaseModel):
    speaker: str
    speaker_role: Optional[str] = None
    party: Optional[str] = None
    position_type: Optional[str] = None
    turn_count: int


class MeetingOverview(BaseModel):
    source_id: Optional[str] = None
    meeting_date: str
    committee: str
    meeting_session: Optional[str] = None
    meeting_round: Optional[str] = None
    meeting_label: Optional[str] = None
    total_turns: int
    speaker_count: int
    party_distribution: dict[str, int]
    govt_turn_count: int
    top_speakers: list[SpeakerStat]
    issue_tags: list[str]


class TurnItem(BaseModel):
    turn_index: Optional[int] = None
    speaker: Optional[str] = None
    speaker_role: Optional[str] = None
    party: Optional[str] = None
    position_type: Optional[str] = None
    utterance_type: Optional[str] = None
    content_preview: str
    source_id: Optional[str] = None
    page_no: Optional[int] = None


class QAPair(BaseModel):
    q_turn_index: Optional[int] = None
    q_speaker: Optional[str] = None
    q_speaker_role: Optional[str] = None
    q_party: Optional[str] = None
    q_preview: str
    q_full_text: str = ""
    q_source_id: Optional[str] = None
    q_page_no: Optional[int] = None
    a_turn_index: Optional[int] = None
    a_speaker: Optional[str] = None
    a_speaker_role: Optional[str] = None
    a_preview: str
    a_full_text: str = ""
    a_source_id: Optional[str] = None
    a_page_no: Optional[int] = None
    confidence: float = 1.0
    needs_review: bool = False
    match_keywords: list[str] = []
    importance: float = 0.0


@app.get("/meetings/{meeting_key}/overview", response_model=MeetingOverview, summary="회의 개요")
def meeting_overview(meeting_key: str):
    """특정 PDF 회의록의 개요 — 발언 수, 정당 분포, 주요 발언자, 쟁점 태그를 반환합니다."""
    try:
        import psycopg2.extras
        where_sql, where_params = _meeting_scope(meeting_key)
        with _db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

                # 기본 집계
                cur.execute(f"""
                    SELECT
                        MIN(source_id) AS source_id,
                        MIN(metadata->>'meeting_date') AS meeting_date,
                        COALESCE(metadata->>'committee', '알 수 없음') AS committee,
                        COUNT(*) AS total_turns,
                        COUNT(DISTINCT speaker) FILTER (WHERE speaker IS NOT NULL AND speaker <> '') AS speaker_count,
                        COUNT(*) FILTER (WHERE metadata->>'position_type' = '정부측') AS govt_turn_count
                    FROM chunks_v2
                    WHERE {where_sql}
                      AND section_type = 'body'
                    GROUP BY committee
                    LIMIT 1
                """, where_params)
                base = cur.fetchone()
                if not base:
                    raise HTTPException(status_code=404, detail=f"{meeting_key} 회의 데이터가 없습니다.")

                # 정당별 발언 수
                cur.execute(f"""
                    SELECT metadata->>'party' AS party, COUNT(*) AS cnt
                    FROM chunks_v2
                    WHERE {where_sql}
                      AND section_type = 'body'
                      AND metadata->>'party' IS NOT NULL
                      AND metadata->>'party' NOT IN ('', '미확인')
                    GROUP BY party
                    ORDER BY cnt DESC
                """, where_params)
                party_dist = {r["party"]: r["cnt"] for r in cur.fetchall()}

                # 주요 발언자 top 10
                cur.execute(f"""
                    SELECT speaker, speaker_role,
                           metadata->>'party' AS party,
                           metadata->>'position_type' AS position_type,
                           COUNT(*) AS turn_count
                    FROM chunks_v2
                    WHERE {where_sql}
                      AND section_type = 'body'
                      AND speaker IS NOT NULL AND speaker <> ''
                    GROUP BY speaker, speaker_role, party, position_type
                    ORDER BY turn_count DESC
                    LIMIT 10
                """, where_params)
                top_speakers = [SpeakerStat(**r) for r in cur.fetchall()]

                # 쟁점 태그용 텍스트 수집
                cur.execute(f"""
                    SELECT clean_text FROM chunks_v2
                    WHERE {where_sql}
                      AND section_type = 'body'
                """, where_params)
                texts = [r["clean_text"] for r in cur.fetchall()]

        meeting_number = _meeting_number_info(str(base["source_id"] or ""))
        return MeetingOverview(
            source_id=base["source_id"],
            meeting_date=base["meeting_date"] or meeting_key,
            committee=base["committee"],
            meeting_session=meeting_number["meeting_session"],
            meeting_round=meeting_number["meeting_round"],
            meeting_label=meeting_number["meeting_label"],
            total_turns=base["total_turns"],
            speaker_count=base["speaker_count"],
            party_distribution=party_dist,
            govt_turn_count=base["govt_turn_count"],
            top_speakers=top_speakers,
            issue_tags=_extract_issue_tags(texts),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB 오류: {e}")


@app.get("/meetings/{meeting_key}/turns", response_model=list[TurnItem], summary="발언 타임라인")
def meeting_turns(meeting_key: str, limit: int = 300):
    """특정 PDF 회의록의 발언을 순서대로 반환합니다."""
    try:
        import psycopg2.extras
        where_sql, where_params = _meeting_scope(meeting_key)
        with _db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(f"""
                    SELECT
                        turn_index,
                        speaker,
                        speaker_role,
                        metadata->>'party'          AS party,
                        metadata->>'position_type'  AS position_type,
                        metadata->>'utterance_type' AS utterance_type,
                        LEFT(clean_text, 200)        AS content_preview,
                        source_id,
                        page_no
                    FROM chunks_v2
                    WHERE {where_sql}
                      AND section_type = 'body'
                    ORDER BY turn_index ASC NULLS LAST, id ASC
                    LIMIT %s
                """, (*where_params, limit))
                rows = cur.fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail=f"{meeting_key} 회의 데이터가 없습니다.")
        return [TurnItem(**r) for r in rows]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB 오류: {e}")


# ── Q&A 매칭 헬퍼 ────────────────────────────────────────────────

_QA_STOPWORDS: set[str] = {
    "있습니다", "없습니다", "합니다", "됩니다", "것입니다", "하는", "있는",
    "그리고", "하지만", "때문에", "관련", "대한", "위한", "통해", "되는",
    "이런", "우리", "그것", "이것", "많은", "모든", "어떤", "대해서", "대해",
    "있어서", "없어서", "이라고", "것으로", "이라는", "하겠습니다", "드립니다",
    "말씀", "위원", "장관", "의원", "위원장", "하셨는데", "하셨습니까",
    "생각합니다", "보입니다", "경우에", "경우는", "부분이", "부분을", "부분에",
}

_BUDGET_KEYWORDS: set[str] = {
    "예산", "증액", "감액", "얼마", "억", "조", "총액", "편성", "배정", "집행",
    "삭감", "요구액", "세출", "세입", "추경", "교부",
}

# 쟁점·중요 발언에 등장하는 키워드
_ISSUE_KEYWORDS: set[str] = {
    "비판", "문제", "우려", "책임", "부족", "미흡", "위반", "지적", "개선",
    "대책", "촉구", "요구", "강화", "점검", "부실", "불법", "위법", "시정",
    "조치", "처벌", "의혹", "부당", "실패", "한계", "해결", "필요", "왜",
    "중단", "취소", "철회", "재검토", "즉각", "반드시", "심각", "중대",
}


def _calc_importance(q_text: str, a_text: str, confidence: float) -> float:
    """Q&A 쌍의 중요도 점수 (0~1).

    importance = length_score*0.3 + issue_score*0.4 + entity_score*0.2 + confidence*0.1

    - length_score : 질의+답변 공백 제외 총 길이 (600자 기준 정규화)
    - issue_score  : 쟁점 키워드 포함 수 (5개 기준 정규화) — 가장 가중치 큼
    - entity_score : 4글자 이상 고유명사 종류 수 (10개 기준 정규화)
    - confidence   : 매칭 신뢰도 그대로 반영
    """
    combined = q_text + " " + a_text

    total_len = len(q_text.replace(" ", "")) + len(a_text.replace(" ", ""))
    length_score = min(1.0, total_len / 600)

    issue_count = sum(1 for kw in _ISSUE_KEYWORDS if kw in combined)
    issue_score = min(1.0, issue_count / 5)

    entities = set(re.findall(r"[가-힣]{4,}", combined)) - _QA_STOPWORDS
    entity_score = min(1.0, len(entities) / 10)

    return round(
        length_score * 0.3 + issue_score * 0.4 + entity_score * 0.2 + confidence * 0.1,
        3,
    )

_TRIVIAL_RE = re.compile(
    r"^(알겠습니다|네|예|아니요|아니오|그렇습니다|맞습니다|좋습니다|감사합니다|"
    r"그러면요|그러면|됐습니다|알아봤습니다|이상입니다|고맙습니다|"
    r"수고하셨습니다|다음으로|이어서|계속해서)[.!?。,\s]*$"
)
_MIN_Q_CHARS = 20

# 실제 질의 텍스트에 있어야 할 패턴 (하나라도 있으면 진짜 질의로 인정)
_QUESTION_MARKERS = re.compile(
    r"(입니까|습니까|인가요|어떻습니까|어떠합니까|않습니까|없습니까|됩니까"
    r"|해주십시오|해주시겠습니까|해주시기|말씀해|알려주|설명해|확인해주|검토해주"
    r"|부탁드립니다|부탁합니다|요청합니다|주시기\s*바랍니다"
    r"|\?|？)"
)

# 정부측 답변 시작에 자주 나오는 패턴
_ANSWER_MARKERS = re.compile(
    r"(^네[,.\s]|^예[,.\s]|^저희|^현재|^말씀드리|^그렇습니다|^확인|^검토"
    r"|^우선|^먼저\s|^일단\s|^구체적으로|^관련하여|^해당\s|^이에\s대해)"
)


def _is_trivial(text: str) -> bool:
    stripped = re.sub(r"\s+", "", text)
    return len(stripped) < _MIN_Q_CHARS or bool(_TRIVIAL_RE.match(text.strip()))


def _is_budget_question(text: str) -> bool:
    return any(kw in text for kw in _BUDGET_KEYWORDS)


def _has_question_marker(text: str) -> bool:
    """실제 질의 패턴이 있는지 확인."""
    return bool(_QUESTION_MARKERS.search(text))


def _has_answer_marker(text: str) -> bool:
    """답변 시작 패턴이 있는지 확인 (첫 100자 기준)."""
    return bool(_ANSWER_MARKERS.search(text[:100]))


def _extract_question_core(full_text: str) -> str:
    """의원 발언 중 실제 질문 문장(마지막 3문장)만 추출 — 매칭 정확도 향상용."""
    sentences = re.split(r"(?<=[.?!。])\s+", full_text.strip())
    if len(sentences) <= 3:
        return full_text
    return " ".join(sentences[-3:])


def _bigram_sim(text1: str, text2: str) -> float:
    """한국어 문자 바이그램 자카드 유사도 (0~1)."""
    def bigrams(t: str) -> set[str]:
        t = re.sub(r"\s+", "", t)
        return {t[i:i + 2] for i in range(len(t) - 1)}
    a, b = bigrams(text1), bigrams(text2)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _shared_keywords(q_text: str, a_text: str) -> list[str]:
    """질의·답변에 공통으로 등장하는 2글자 이상 한국어 단어 (상위 5개)."""
    q_words = set(re.findall(r"[가-힣]{2,}", q_text))
    a_words = set(re.findall(r"[가-힣]{2,}", a_text))
    shared = (q_words & a_words) - _QA_STOPWORDS
    return sorted(shared, key=len, reverse=True)[:5]


def _entity_overlap_bonus(q_text: str, a_text: str) -> float:
    """질의·답변에 공통으로 등장하는 고유명사(기관명·사업명 등) 겹침 보너스.

    바이그램 유사도가 낮아도 같은 기관명/사업명이 등장하면 실제 매칭일 가능성이 높음.
    - 4글자 이상 공통 단어: 기관명·사업명 가능성 높음 → 건당 +0.07
    - 3글자 공통 단어: 일반 핵심어 → 건당 +0.04
    - 최대 0.18 (3개 기관명 수준)
    """
    q_words = set(re.findall(r"[가-힣]{3,}", q_text))
    a_words = set(re.findall(r"[가-힣]{3,}", a_text))
    shared = (q_words & a_words) - _QA_STOPWORDS
    bonus = 0.0
    for w in shared:
        bonus += 0.07 if len(w) >= 4 else 0.04
    return min(0.18, bonus)


def _score_candidate(q_full: str, a_full: str, block_distance: int, is_direct: bool) -> tuple[float, float, list[str]]:
    """(confidence, topic_sim, keywords) 반환.

    질문 핵심부(마지막 3문장)와 답변 전문의 유사도를 함께 사용해
    앞부분 설명이 긴 의원 발언의 매칭 정확도를 높인다.
    """
    q_core = _extract_question_core(q_full)
    topic_full = _bigram_sim(q_full, a_full)
    topic_core = _bigram_sim(q_core, a_full)
    topic = max(topic_full, topic_core)  # 둘 중 높은 쪽 사용

    proximity = max(0.0, 1.0 - (block_distance - 1) / 5.0)
    directness = 1.0 if is_direct else 0.65

    # 패턴 보너스: 질의 마커 있으면 +0.05, 답변 마커 있으면 +0.05
    pattern_bonus = (0.05 if _has_question_marker(q_full) else 0.0) \
                  + (0.05 if _has_answer_marker(a_full) else 0.0)

    # 고유명사 겹침 보너스: 같은 기관명·사업명이 양쪽에 등장하면 신뢰도 상향
    entity_bonus = _entity_overlap_bonus(q_full, a_full)

    confidence = round(
        topic * 0.5 + proximity * 0.3 + directness * 0.2 + pattern_bonus + entity_bonus,
        2
    )
    keywords = _shared_keywords(q_core, a_full)
    return confidence, topic, keywords


def _build_qa_blocks(rows: list[dict]) -> list[dict]:
    """연속된 같은 발언자·position 턴을 하나의 발언 블록으로 묶는다."""
    blocks: list[dict] = []
    i = 0
    while i < len(rows):
        turn = rows[i]
        group = [turn]
        j = i + 1
        while j < len(rows):
            nxt = rows[j]
            if (nxt.get("speaker") == turn.get("speaker")
                    and nxt.get("position_type") == turn.get("position_type")):
                group.append(nxt)
                j += 1
            else:
                break
        previews = [t.get("content_preview") or "" for t in group]
        fulls = [t.get("full_text") or "" for t in group]
        full_text = "\n".join(fulls)
        position_type = turn.get("position_type") or ""
        speaker_role = turn.get("speaker_role") or ""
        # DB 태깅 오류를 보정: 개선된 패턴으로 재추론
        re_inferred = _infer_utype(full_text, speaker_role=speaker_role, position_type=position_type)
        blocks.append({
            "speaker": turn.get("speaker"),
            "speaker_role": speaker_role,
            "party": turn.get("party"),
            "position_type": position_type,
            "utterance_type": re_inferred,
            "turn_index": turn.get("turn_index"),
            "preview": " ".join(previews)[:500],
            "full_text": full_text,
            "source_id": turn.get("source_id"),   # 블록 첫 턴 기준
            "page_no": turn.get("page_no"),
        })
        i = j
    return blocks


_CONF_MIN = 0.4      # 이 미만이면 쌍 생성 안 함
_CONF_REVIEW = 0.6   # 이 미만이면 needs_review = True
_TOPIC_MIN = 0.05    # 바이그램 유사도 최소 하한


@app.get("/meetings/{meeting_key}/qa_pairs", response_model=list[QAPair], summary="질의-답변 쌍")
def meeting_qa_pairs(meeting_key: str):
    """
    위원 질의 → 정부측 답변을 발언 블록 단위로 매칭합니다.

    매칭 방식:
    - 연속 같은 발언자 턴을 하나의 블록으로 묶음
    - 질문 블록 뒤 범위 내 정부측 후보를 모두 수집
    - topic · proximity · directness로 확신 점수 계산 후 최고 점수 후보 선택
    - 공통 핵심어 없음 / topic < 0.05 / confidence < 0.4 이면 쌍 버림
    - 예산 관련 질문은 답변에도 예산 단어 있어야 매칭
    - 너무 짧거나 의미 없는 질문 블록 제외
    """
    try:
        import psycopg2.extras
        where_sql, where_params = _meeting_scope(meeting_key)
        with _db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(f"""
                    SELECT
                        turn_index,
                        speaker,
                        speaker_role,
                        metadata->>'party'          AS party,
                        metadata->>'position_type'  AS position_type,
                        metadata->>'utterance_type' AS utterance_type,
                        LEFT(clean_text, 500)        AS content_preview,
                        clean_text                   AS full_text,
                        source_id,
                        page_no
                    FROM chunks_v2
                    WHERE {where_sql}
                      AND section_type = 'body'
                    ORDER BY turn_index ASC NULLS LAST, id ASC
                    LIMIT 500
                """, where_params)
                rows = [dict(r) for r in cur.fetchall()]

        if not rows:
            raise HTTPException(status_code=404, detail=f"{meeting_key} 회의 데이터가 없습니다.")

        blocks = _build_qa_blocks(rows)
        used: set[int] = set()
        pairs: list[QAPair] = []

        for bi, block in enumerate(blocks):
            if bi in used:
                continue
            if block["position_type"] != "의원":
                continue
            if block["utterance_type"] != "question":
                continue
            # 너무 짧거나 무의미한 질문 제외
            if _is_trivial(block["full_text"]):
                continue
            # 실제 질의 패턴(물음표·요청어)이 없으면 설명 발언으로 간주하고 제외
            if not _has_question_marker(block["full_text"]):
                continue

            is_budget_q = _is_budget_question(block["full_text"])

            # ── 후보 수집 ─────────────────────────────────────────
            candidates: list[dict] = []
            for bj in range(bi + 1, min(bi + 7, len(blocks))):
                if bj in used:
                    continue
                nxt = blocks[bj]

                # 다른 의원의 새 질의 → 이 질의 구간 종료
                if (nxt["position_type"] == "의원"
                        and nxt["utterance_type"] == "question"
                        and nxt["speaker"] != block["speaker"]):
                    break

                if (nxt["position_type"] != "정부측"
                        or nxt["utterance_type"] not in ("answer", "statement")):
                    continue

                # 예산 관련 질문: 답변에도 예산 단어 있어야 함
                if is_budget_q and not any(kw in nxt["full_text"] for kw in _BUDGET_KEYWORDS):
                    continue

                conf, topic, kws = _score_candidate(
                    block["full_text"], nxt["full_text"],
                    block_distance=bj - bi,
                    is_direct=nxt["utterance_type"] == "answer",
                )
                candidates.append({"bj": bj, "nxt": nxt, "conf": conf, "topic": topic, "kws": kws})

            if not candidates:
                continue

            # ── 최고 점수 후보 선택 ───────────────────────────────
            best = max(candidates, key=lambda c: c["conf"])

            # 품질 기준 미달 → 버림
            if not best["kws"]:
                continue
            if best["topic"] < _TOPIC_MIN:
                continue
            if best["conf"] < _CONF_MIN:
                continue

            imp = _calc_importance(block["full_text"], best["nxt"]["full_text"], best["conf"])
            pairs.append(QAPair(
                q_turn_index=block["turn_index"],
                q_speaker=block["speaker"],
                q_speaker_role=block["speaker_role"],
                q_party=block["party"],
                q_preview=block["preview"],
                q_full_text=block["full_text"],
                q_source_id=block.get("source_id"),
                q_page_no=block.get("page_no"),
                a_turn_index=best["nxt"]["turn_index"],
                a_speaker=best["nxt"]["speaker"],
                a_speaker_role=best["nxt"]["speaker_role"],
                a_preview=best["nxt"]["preview"],
                a_full_text=best["nxt"]["full_text"],
                a_source_id=best["nxt"].get("source_id"),
                a_page_no=best["nxt"].get("page_no"),
                confidence=best["conf"],
                needs_review=best["conf"] < _CONF_REVIEW,
                match_keywords=best["kws"],
                importance=imp,
            ))
            used.add(bi)
            used.add(best["bj"])

        # 중요도 내림차순 정렬 후 반환
        pairs.sort(key=lambda p: p.importance, reverse=True)
        return pairs
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB 오류: {e}")
