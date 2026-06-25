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

import json
import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

_STREAM_MAX_TOKENS = int(os.getenv("GENERATE_MAX_TOKENS", "1024"))
_CITE_FALLBACK = 5

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
    committee: Optional[str] = Field("외교통일위원회", description="위원회 필터")
    top_k: int = Field(5, ge=1, le=20, description="검색 청크 수")
    use_fusion: bool = Field(True, description="Fusion 검색(BM25+벡터 RRF) 활성화")
    use_neural_reranker: bool = Field(True, description="Neural Reranker 활성화")


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
    committee: str
    meeting_date: str
    doc_count: int


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
        "committee": req.committee or "외교통일위원회",
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

            meta = {
                "top_k": min(req.top_k, 4),   # Jina top-4: 5번째 chunk의 주제 이탈 방지
                "rerank_n": min(req.top_k, 4),
                "committee": req.committee or "외교통일위원회",
                "use_fusion": req.use_fusion,
                "use_neural_reranker": True,  # JinaReranker API (~0.5s) or local fallback
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
            user_prompt = build_user_prompt(
                state.get("question", ""),
                state.get("context", ""),
                reference_date=date.today(),
                doc_name_query=bool((state.get("meta") or {}).get("doc_name_query")),
                question_type=(state.get("meta") or {}).get("question_type", ""),
            )

            _reasoning = needs_reasoning_model(req.question)
            _gen_model = os.getenv("OPENAI_REASONING_MODEL", "gpt-4o") if _reasoning else None
            tokens: list[str] = []
            for token in _stream_openai(system_prompt, user_prompt, max_tokens=_STREAM_MAX_TOKENS, model=_gen_model):
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
    """적재된 회의록의 위원회·날짜·청크 수를 반환합니다."""
    sql = """
    SELECT
        metadata->>'committee'    AS committee,
        metadata->>'meeting_date' AS meeting_date,
        COUNT(*)                  AS doc_count
    FROM chunks_v2
    WHERE section_type = 'body'
      AND metadata->>'committee' IS NOT NULL
      AND metadata->>'meeting_date' IS NOT NULL
    GROUP BY 1, 2
    ORDER BY 2 DESC, 1
    LIMIT 200
    """
    try:
        import psycopg2.extras
        with _db_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        return [MeetingItem(**r) for r in rows]
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
