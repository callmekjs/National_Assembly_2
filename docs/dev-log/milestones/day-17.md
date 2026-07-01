# Day 17 — 프로토타입 완성 · 문서화 · 배포

> 완료일: 2026-06-30 ~ 2026-07-01

---

## 주요 성과 요약

| 항목 | 내용 |
|------|------|
| eval 최종 결과 | 66/75 (88%) — 알고리즘 #6·#7 포함 4회차 |
| Vercel 배포 | 프론트엔드 national-assembly-2.vercel.app |
| 문서화 완료 | README, ARCHITECTURE, EVALUATION, MEMORY, Day17 마일스톤 |
| 개발과정 다이어그램 | 스크린샷/개발과정.jpg (matplotlib 생성) |

---

## 1. Eval 4회차 최종 실행 (2026-06-30)

결과 파일: `eval/results/results_20260630_160145.json`

| 지표 | 결과 |
|------|------|
| grounding_ok (FULL+PARTIAL) | 66/75 (88%) |
| FULL | 54건 |
| PARTIAL | 12건 |
| REFUSED (올바른 거절) | 4건 |
| NONE | 5건 |
| latency <10s | 75/75 (100%) |

---

## 2. 배포 (Vercel 프론트엔드)

- `frontend/` Vite 빌드 → Vercel 배포
- URL: `national-assembly-2.vercel.app`
- 환경변수: `VITE_API_BASE` (백엔드 로컬 URL 설정)
- 백엔드는 BGE-M3 RAM(2.2GB) 문제로 로컬 전용

---

## 3. 개발과정 다이어그램 생성

`스크린샷/make_diagram.py` — matplotlib으로 7단계 개발 과정 시각화:
- 기획[완료] → 설계[완료] → 개발[완료] → 소스관리[완료] → 배포[절반] → 출시[미완] → 유지보수[완료]
- 하단 요약: 완료 성과·한계·포트폴리오 계획
- 출력: `스크린샷/개발과정.jpg`

---

## 4. 전체 문서 업데이트

| 파일 | 변경 내용 |
|------|-----------|
| `README.md` | 전면 재작성 — 최종 수치·3위원회·알고리즘7개·배포현황 |
| `docs/architecture/ARCHITECTURE.md` | BGE-M3 기준 재작성, 알고리즘 시리즈 표 추가 |
| `docs/evaluation/EVALUATION.md` | 4회차 eval 이력, 실패 9건 분석, 데이터 품질 갱신 |
| `llm_evaluation.md` | 75문항 전체 결과 테이블 (이전 세션에서 작성 완료) |
| `docs/dev-log/milestones/day-17.md` | 본 파일 |

---

## 5. 프로토타입 현황 (종료 기준)

### 완료된 것

- ETL 파이프라인 7단계 (3개 위원회, 78,952행)
- LangGraph RAG 파이프라인 (7노드)
- 하이브리드 검색 (BGE-M3 Dense + BM25 Sparse + RRF + Rerank)
- Grounding Check (FULL/PARTIAL/REFUSED/NONE)
- 하이브리드 모델 라우팅 (gpt-4o-mini / gpt-4o)
- 75문항 eval 파이프라인
- 111개 단위 테스트
- React 프론트엔드 (SSE 스트리밍, 위원회 탭, 멀티턴)
- Vercel 프론트엔드 배포

### 미완성 (포트폴리오에서 구현 예정)

- 백엔드 클라우드 배포 (BGE-M3 → OpenAI Embedding API로 경량화 후)
- 로그인/회원가입
- 커스텀 도메인
- eval 실패 9건 수정

---

## 다음 (포트폴리오 버전)

별도 저장소에서 처음부터 재구현:
1. OpenAI Embedding API로 교체 → 경량화
2. 전체 배포 (프론트 + 백엔드)
3. 로그인/회원가입
4. 완성도 높은 UI/UX
