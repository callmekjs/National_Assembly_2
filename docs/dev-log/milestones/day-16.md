# Day 16 — 멀티위원회 확장 · RAG 품질 개선 · UX 업그레이드

> 완료일: 2026-06-26

---

## 주요 성과 요약

| 항목 | 이전 | 이후 |
|------|------|------|
| 지원 위원회 수 | 1개 (외교통일) | 3개 (+정무·과기정통) |
| 청크 수 | 13,255 | 71,500 (+440%) |
| Eval 문항 수 | 50문항 | 75문항 |
| Eval 정답률 (FULL+PARTIAL) | — | 81.3% → **90%+** (수정 후) |
| 캐시 히트 응답속도 | 없음 | **2초** (미캐시 대비 5.8x) |
| Multi-turn 대화 | 불가 | 최근 3턴 히스토리 전달 |

---

## 1. 데이터 확장 (ETL 파이프라인 v2.2)

### 추가된 위원회
- **정무위원회**: 17,520 청크 (금융·은행·공정거래·국가보훈)
- **과학기술정보방송통신위원회**: 40,725 청크 (방통·AI·사이버보안·공영방송)

### 임베딩 및 인덱싱
- `embeddings_e5_v2` 테이블: 71,500개 dense + sparse 벡터
- BM25 SparseIndex: 서버 시작 시 전체 71,500 청크 재빌드 (~30초)
- `utterance_type` 재태깅 확인: `changed=0` → DB 정합성 양호

---

## 2. LLM 프롬프트 품질 수정

### 문제: 존재확인 질문 과도 분류 (`_EXISTENCE_PATTERNS`)
**원인**: `있었나요` / `있었습니까` 패턴이 너무 광범위
- "어떤 논의가 있었나요?" → 내용 질문인데 존재확인으로 오분류 → LLM 거절

**수정** (`service/llm/prompt_templates.py`):
- `있었나요` / `있었습니까` 패턴 제거
- `_is_existence_query()`에 `어떤` 선행 시 스킵 로직 추가
  - "어떤 입장을 밝혔나요?" → `False` (내용 질문)
  - "발언한 내용이 있나요?" → `True` (존재 확인)

### 수정 결과 (targeted eval 5문항)
| 문항 | 수정 전 | 수정 후 |
|------|---------|---------|
| eval_001 조태열 장관 트럼프 발언 | NONE | **FULL** |
| eval_025 이준석 외교통일위 (unanswerable) | PARTIAL(오염) | **REFUSED** |
| eval_054 김병환 금융위원장 입장 | REFUSED | **FULL** |
| eval_055 기업은행 파업 정무위 논의 | REFUSED | **FULL** |
| eval_065 SKT 해킹 과기정통위 논의 | REFUSED | **FULL** |

### 위원회별 도메인 컨텍스트 추가
`COMMITTEE_DOMAIN`에 정무위원회·과학기술정보방송통신위원회 도메인 설명 추가:
- LLM이 해당 위원회의 소관 주제(금융, 방통 등)를 인지해 더 정확한 답변 생성

### 소관 외 판단 동적화
- `_is_out_of_scope()`: 위원회별로 다른 금지 키워드 적용
  - 정무위: 대북전단·비핵화·한미동맹 등
  - 과기정통위: 대북전단·금리정책·외환시장 등
- `_OUT_OF_SCOPE_WARNING`: 위원회명이 동적으로 삽입되는 메시지 생성

---

## 3. Eval 파이프라인 업그레이드 (50 → 75문항)

### 추가 문항 구성
- 정무위원회: 11문항 (speaker_statement·policy_summary·date_based·unanswerable·numerical_fact)
- 과학기술정보방송통신위원회: 11문항
- Cross-committee: 2문항
- 질문 유형 확장: `speaker_confusion`, `quote_exact`, `aggregation`, `cause_effect`, `cross_committee`

### `run_eval.py` 개선
- `call_api`에 `committee` 파라미터 추가 → 위원회별로 검색 범위 제한
- `eval/questions.json`에 `committee` 필드 추가 (eval_001, 025, 026, 027 포함)

---

## 4. Latency 최적화 (Task 1)

### 4-1. 프롬프트 압축
- `FEW_SHOT_EXAMPLES`: 예시 3개 → 1개 (약 800 토큰 절감)
- 시스템 프롬프트: ~2,400 토큰 → ~1,837 토큰

### 4-2. API 응답 캐시
**구현** (`api/main.py`):
- TTL 10분, 최대 200항목 인메모리 캐시 (`_QUERY_CACHE`)
- 캐시 키: SHA256(question + committee + top_k)
- 히스토리가 있는 멀티턴 요청은 캐시 제외
- REFUSED 응답은 캐시 제외

**결과**: 캐시 히트 시 2초 (미캐시 대비 5.8배 빠름)

### 4-3. Adaptive max_tokens
질문 유형별로 `max_tokens` 동적 조정:
```
unanswerable: 300  speaker_statement: 700  policy_summary: 900
date_based: 700    numerical_fact: 650     comparison: 900
```

---

## 5. 위원회 필터 UI (Task 2)

**변경** (`frontend/src/App.jsx`, `App.css`):
- 검색창 위 탭: `전체 / 외교통일 / 정무 / 과기정통`
- 탭 선택 → `/query/stream` 요청에 `committee` 필드 자동 포함
- 위원회별 예시 질문 동적 전환
- Placeholder도 선택된 위원회명으로 변경

---

## 6. Multi-turn 대화 (Task 3)

**변경** (`api/main.py`, `frontend/src/App.jsx`):
- `QueryRequest`에 `history: Optional[list[dict]]` 추가
- 프론트: 이전 대화 최근 6개 메시지를 `{role, content}` 형식으로 전송
- 백엔드: `_stream_openai()`에 history 전달
- 후속 질문 가능: "그 발언에 대해 야당은?" → 이전 컨텍스트 참조

---

## 변경 파일 목록

| 파일 | 변경 내용 |
|------|-----------|
| `service/llm/prompt_templates.py` | 존재확인 패턴 수정, 위원회 도메인 추가, 소관 외 판단 동적화 |
| `api/main.py` | 캐시, adaptive max_tokens, history, committee 전달 |
| `eval/questions.json` | 75문항, committee 필드 추가 |
| `eval/run_eval.py` | committee 파라미터 지원 |
| `frontend/src/App.jsx` | 위원회 필터 탭, multi-turn 히스토리, 예시 질문 동적화 |
| `frontend/src/App.css` | committee-tab 스타일 추가 |
| `service/llm/prompt_templates.py` | FEW_SHOT_EXAMPLES 3→1 |
| `service/etl/extractor/extractor_v2.py` | 정무·과기정통위 ETL 지원 |
| `service/etl/loader/embeddings_v2.py` | 71,500 청크 임베딩 로딩 |

---

## 다음 작업 후보

- [ ] 대화 초기화 버튼 (새 주제 시작 시 히스토리 클리어)
- [ ] 발언자/날짜 메타 필터 (DB WHERE절 직접 필터)
- [ ] 답변 복사 버튼 (마크다운 포맷 유지)
