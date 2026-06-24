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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="국회 회의록 RAG API",
    description="외교통일위원회 회의록 기반 근거 인용 질의응답",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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

    citations: list[Citation] = []
    for i, doc in enumerate(docs[:10], start=1):
        meta_doc = doc.get("metadata") or {}
        citations.append(Citation(
            index=i,
            speaker=meta_doc.get("speaker") or doc.get("speaker"),
            date=meta_doc.get("meeting_date") or doc.get("date"),
            committee=meta_doc.get("committee"),
            content_preview=(doc.get("content") or "")[:120],
        ))

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
