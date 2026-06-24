# Changelog

지금까지 **완성된 마일스톤** 요약입니다. 상세 구현·파일 변경은 [docs/dev-log/](docs/dev-log/)를 참고하세요.

형식: [Keep a Changelog](https://keepachangelog.com/) 스타일 (날짜 역순).

---

## [재현성 진단 · 개선 방향 정의] 2026-06-24

### Investigated
- **재현성 문제 진단**: 재실행마다 세부근거·참고자료가 바뀌는 원인이 Rerank가 아닌 `temperature=0.7` (`llm_client.py:167, 239`)임을 확인
  - `graph/nodes/rerank.py`는 점수 내림차순 정렬만 수행, 실제 Neural Reranker(`BAAI/bge-reranker-v2-m3`)는 `search_v2()` 내부에서 인라인 실행 — 이미 결정적(deterministic)
  - 실무 해결 패턴 3단계: ① temperature 인하 + seed 고정 (5분) → ② 응답 캐시 exact/semantic (운영 표준) → ③ JSON 구조화 출력으로 인용 번호 안정화

---

## [Day 14 패키징 · Day 15 발표 마감] 2026-06-24

재현성 패키징, E2E 통합 테스트, 발표 포트폴리오 패키지 완성.

### Added
- **E2E 통합 테스트** (`tests/conftest.py`, `tests/test_e2e_pipeline.py`):
  - `--pg-port` pytest CLI 옵션 + session 스코프 DB 픽스처
  - DB → chunks → embeddings_e5 → Retriever.search → Generator.generate_with_citations 전 과정 5단계 검증
  - DB 미연결 환경 자동 skip (CI 안전)
- **Healthcheck CLI** (`scripts/healthcheck.py`):
  - Postgres 연결·chunks·embeddings_e5·벡터차원 4단계 진단
  - `.env` 자동 로드, CLI 인자 > 환경변수 > 기본값, Windows UTF-8 호환
  - 단계 실패 시 이후 SKIP + exit(1)
- **발표 포트폴리오 패키지** (`docs/presentation/day15-package.md`):
  - 60초 서사 (3문장 구어체), 데모 질문 3개 스크립트 + 실패 대사, Mermaid 아키텍처 다이어그램, 핵심 수치 스냅샷

### Changed
- **README** (`README.md`): 서비스 구성 표 + 빠른 시작 4단계 (`healthcheck.py` 포함) 추가
- **Day 14 마일스톤** (`docs/dev-log/milestones/day-14.md`): 원데이 검증 노트로 교체
- **Day 15 마일스톤** (`docs/dev-log/milestones/day-15.md`): 전 항목 완료 체크

---

## [인프라·엔지니어링 4-1/4-2/4-3] 2026-06-23

FastAPI 레이어, 쿼리 모니터링, 핵심 모듈 단위 테스트 구현.

### Added
- **FastAPI 앱** (`api/main.py`): `POST /query` · `GET /meetings` · `GET /health` · Swagger UI `/docs`
  - `POST /query`: LangGraph 파이프라인 호출 → 답변 + citations + latency_ms 반환
  - `GET /meetings`: DB에서 위원회·날짜·청크 수 목록 조회
  - `GET /logs`, `/logs/failures`, `/logs/stats`: 쿼리 로그 모니터링 엔드포인트
- **쿼리 로거** (`service/monitoring/query_logger.py`):
  - `query_logs` 테이블: 질문·답변·grounding_level·doc_count·latency 자동 누적
  - `is_recall_zero` 컬럼: recall=0 질의 자동 감지 + 인덱싱
  - `get_recent_failures()`, `get_stats()`: 검색 실패 분리 조회 및 통계
- **단계별 latency 측정**: `retrieve_pg.py` + `generate.py` 노드에서 ms 단위 측정 → `state["latency_ms"]` 저장 → DB 기록
- **단위 테스트** (`tests/`): 41/41 PASS — DB·모델 없이 mock으로 실행
  - `test_chunker.py`: `_extract_speaker`, `_split_by_sentence`, `_make_chunks` 13개
  - `test_normalizer.py`: `_normalize_text`, `_normalize_metadata` 16개
  - `test_retriever.py`: `_lexical_overlap_score`, `_domain_keyword_boost`, `_balance_speakers` 등 12개

---

## [전체 테스트 통과 · 안정화] 2026-06-23

시스템 테스트 22/22 · 데이터 파이프라인 테스트 13/13 전부 PASS. 디버그 잔재 제거 및 기본 preset 고정.

### Fixed
- **PyMuPDF `bad quads entry`** (`chat.py:1099`): `add_highlight_annot(rect)` → `add_highlight_annot(rect.quad)` — PyMuPDF 1.24.x+ API 변경 대응
- **디버그 출력 제거** (`retrieve_pg.py`): `_trim_dangling_head()` 내 `st.write(text)` 삭제
- **디버그 출력 제거** (`grounding_check.py`): `[DBG_ENTRY]` print 완전 제거

### Changed
- **기본 검색 preset 고정** (`chat.py` `_init_state`): `qa_use_fusion=True`, `qa_use_neural_reranker=True` — Fusion + Neural Reranker 항상 활성화

### Added
- **수동 평가 데이터셋** (`service/rag/eval/eval_dataset_manual.json`): EVALUATION.md 기반 23개 테스트 케이스 (grounding_ood, hallucination, multi_turn, ambiguous 등)
- **CTO 레벨 시스템 테스트 명세** (`docs/test.md`): T-1~T-6 22개 테스트
- **시스템 테스트 결과** (`docs/test_eval.md`): 22/22 PASS
- **데이터 파이프라인 테스트 명세** (`docs/Data_test.md`): D-1~D-6 13개 테스트
- **데이터 파이프라인 테스트 결과** (`docs/Data_test_eval.md`): 13/13 PASS (D-3-2 300자미만 69.9% ⚠️ 발언자 단위 특성상 허용)
- **RAGAS 호환성 수정** (`service/rag/eval/ragas_eval.py`): ragas 0.4.x deprecated singleton API 사용, NaN 가드 추가

### Metrics (2026-06-23 기준)
- recall@3: 100% (10/10)
- RAGAS faithfulness: 0.9857
- 청크: 18,048건 / 중복 0건
- speaker 채움률: 98.6% / committee·meeting_date: 100%

→ [시스템 테스트 결과](docs/test_eval.md) · [데이터 테스트 결과](docs/Data_test_eval.md)

---

## [비교 쿼리 검색 개선] 2026-06-23

비교 질문("A 장관과 B 장관의 차이") 시 두 인물의 직접 발언을 정확히 검색하도록 개선.

### Fixed
- **speaker 필터 추가** (`pgvector_store.py`): `filters`에 `speaker` 키 처리 추가 → `c.metadata->>'speaker' LIKE %s` WHERE절 적용
- **`_expand_query` 하드코딩 제거** (`retriever.py`): "통일부 장관" 조건에서 `"정동영 후보자"`, `"2026-04-23"` 하드코딩 삭제 → 날짜 편향 해소
- **쿼리 오염 수정** (`retrieve_pg.py`): 비교 쿼리 분리 검색 시 `other_kw` 전체 제거 → 공유 직함("장관")까지 삭제되는 버그 수정, 이름(`other_name`)만 제거하도록 변경

### Changed
- **`retriever.search()`** (`retriever.py`): `speaker: str | None = None` 파라미터 추가 → `filters`에 포함해 `pgvector_store`로 전달
- **비교 쿼리 `per_k`** (`retrieve_pg.py`): `top_k // 2` → `max(top_k * 2, 15)` — 인물마다 주제 관련도 편차가 있어 충분히 넓게 탐색
- **인물별 분리 검색** (`retrieve_pg.py`): `name1/name2` 미사용 dead code 제거, 각 인물 검색 시 `speaker=speaker_name` 필터 적용

### Root cause
조태열(외교부장관) 발언이 기본 `top_k=8` 안에 들어오지 않던 이유: 쿼리에 상대 인물명이 섞이고(`_expand_query` 하드코딩), `per_k`가 절반으로 줄어들면서 벡터 유사도 랭킹에서 밀렸던 것. 수정 후 기본값으로도 두 인물 직접 발언이 모두 검색됨.

---

## [3-1·3-2 완료] 2026-06-22

LLM 생성 품질 고도화 — 답변 품질 (3-1) 완료.

### Added
- **대화 히스토리 (멀티턴)**: 이전 Q&A 최대 3턴을 OpenAI messages 배열에 삽입 — 후속 질문 문맥 유지
  - `llm_client.py`: `chat_stream` / `chat` / `_chat_openai` / `_stream_openai` / `_chat_local_hf` 전부 `history` 파라미터 추가
  - `chat.py`: `_build_history()` — 현재 세션 메시지에서 인용 블록 제거 후 최근 N턴 추출
- **답변 신뢰도 표시**: 검색 결과 수 + 평균 유사도를 답변 하단에 한 줄 노출
  - `chat.py`: `_confidence_line(docs)` — `> 🔍 검색 결과 N개 · 평균 유사도 0.XX` 형식

- **위원회 도메인 프롬프트**: `COMMITTEE_DOMAIN` 5개 위원회 컨텍스트 → `build_system_prompt(committee=)` 파라미터 추가
- **GroundingCheck 강화**: 검색 결과 있는데 `[n]` 인용 없으면 경고 문구 자동 삽입 (비스트리밍·스트리밍 양 경로)
- **출처 신뢰도 등급**: 참고 자료 테이블에 `신뢰도` 열 추가 — ⭐높음/△보통/▽낮음 (날짜 정상·발언자 있음 기준)

→ [상세 일지](docs/dev-log/2026-06-22.md)

---

## [고도화] 2026-06-21

RAG 검색·평가·데이터 파이프라인 대규모 고도화 스프린트.

### Added
- **스트리밍 응답**: `chat_stream()` + Streamlit `write_stream`, LangGraph `skip_generate`
- **검색 전략**: Multi-query, HyDE, Fusion(BM25+RRF), Parent doc, Step-back, Contextual compression
- **리랭킹**: Neural (`bge-reranker-v2-m3`), LLM reranker, MMR, Score norm, Ensemble
- **평가**: RAGAS 4지표, 평가셋 50문항, A/B 8전략 비교 (`ab_compare`)
- **ETL**: 발언자(◯) 단위 청킹 + overlap → 18,048청크, Contract, quality 리포트, run_history, incremental embed
- **Notion 동기화**: `notion_sync.py`

### Removed
- 미사용 `rag_system.py`, `augmentation/`, `cleanup_system.py` (~1,050줄)

→ [상세 일지](docs/dev-log/2026-06-21.md)

---

## [v1 운영] 2026-05-10

생성 경로·OpenAI 연동·인용 UX 강화.

### Added
- OpenAI Chat API 우선 + 로컬 HF 폴백 (`llm_client.py`)
- `llm_env_probe()`, 생성 실패 유형 구분 (`llm_error_kind`)
- 참고 자료 pandas 테이블, 프롬프트 발언자·날짜·질문 주체 규칙 강화
- Day 12~13: 날짜 역전 보정, `smoke_day13.py`, `OPERATIONS.md` 민감도

→ [상세 일지](docs/dev-log/2026-05-10.md) · [Day 12](docs/dev-log/milestones/day-12.md) · [Day 13](docs/dev-log/milestones/day-13.md)

---

## [v1 검색 100%] 2026-05-09

검색 회귀 완료 및 v1 마감.

### Changed
- **recall@3**: 20% → **100%** (고정 eval 10문항, Day 11)
- `candidate_multiplier` 50, 도메인 키워드·구절 가점, 쿼리 확장
- Router meta 병합, Streamlit 검색 설정 UI, 인용 `[n]` 정합

### Added
- `eval_report_day11.json`, `verify_streamlit_citation_alignment`
- `OPERATIONS.md`, `run_pipeline.ps1` idempotent 검증
- README·Streamlit 서사 정렬 (RAG 메인 / ETL 전제)

→ [상세 일지](docs/dev-log/2026-05-09.md) · [Day 6~11](docs/dev-log/milestones/)

---

## [v1 기반] 2026-05-08

파이프라인 재현성·데모 v0.

### Added
- 원클릭 `run_pipeline.ps1`, 스모크 3문항 QA
- 하이브리드 검색 (`alpha`), rule reranker, 발언자 균형
- 인용 포맷 `[n] source/date/quote` 고정 (Day 5)

→ [상세 일지](docs/dev-log/2026-05-08.md) · [Day 3~5](docs/dev-log/milestones/)

---

## [v1 시작] 2026-05-07

엔드투엔드 파이프라인 1회 검증.

### Added
- Crawling → Extract → Transform → Load → pgvector 검색
- `eval_queries.json` (10문항), `evaluate_retrieval`, `qa_demo`
- 외교통일위원회 55건, 초기 청크 4,943개

### Metrics (기준선)
- score 60%, recall@3 20%, mrr@3 0.200

→ [상세 일지](docs/dev-log/2026-05-07.md) · [Day 1~2](docs/dev-log/milestones/)

---

## v1 완료 기준 (달성)

| 항목 | 상태 |
|------|------|
| ETL → Load → Search hits > 0 | ✅ Day 1 |
| Streamlit LLM 답변 + 인용 `[n]` | ✅ Day 4~5 |
| recall@3 100% (고정 eval) | ✅ Day 11 |
| 고급 검색·리랭킹·RAGAS (opt-in) | ✅ 2026-06-21 |
| 스트리밍 UX | ✅ 2026-06-21 |
| 시스템 테스트 22/22 PASS | ✅ 2026-06-23 |
| 데이터 파이프라인 테스트 13/13 PASS | ✅ 2026-06-23 |
| 기본 preset 고정 (Fusion + Neural) | ✅ 2026-06-23 |
| FastAPI 레이어 (POST /query, GET /meetings) | ✅ 2026-06-23 |
| 쿼리 로그·recall=0 감지·단계별 latency | ✅ 2026-06-23 |
| 단위 테스트 41/41 PASS (chunker·normalizer·retriever) | ✅ 2026-06-23 |
| Day 14 배포 패키징 | ⬜ [ROADMAP](ROADMAP.md) |
| Day 15 발표 패키지 | ⬜ [ROADMAP](ROADMAP.md) |
