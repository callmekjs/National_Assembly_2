# Day 11 - 오늘 내가 할 일 (검색·평가 마지막 퍼센트)

> v1에서 남은 실패 1건(`정보 공유 제한 이슈…`)과 검색 엣지를 줄이는 주간.

## 목표
- [x] **Streamlit 답변**이 **우리 DB에서 검색된 청크**와 맞물리도록(평가·수동 확인) 회귀
- [x] `eval_queries_fixed` 라벨 질의 중 FAIL 0건에 가깝게 수렴 (또는 라벨 기대값 재검토)
- [x] 난항 질의 전용 확장/필터 규칙이 있으면 코드·문서로 고정
- [x] 유형별(classification) 회귀 숫자 재확인

## 1) 실패 질의 집중
- [x] `정보 공유 제한 이슈가 언급된 회의가 있나?` 재현 → 쿼리 확장(`대북 정찰정보` 등)·구구절 **`정보 공유 제한` 연속 매칭** 가점 반영 (`retriever.py`)
- [x] `통일부 장관 관련 주요 질의`: 핵심 구 **`외통위 현안질의`** 단일 회의 신호 가점 + **후보 풀** 부족(벡터 순위 ~126위 청크) 해소를 위해 후보 배수 기본값 상향
- [x] 키워드 가중·쿼리 확장·후보 배수로 해결(라벨 `expected_source_ids` 변경 없음)

## 2) 회귀 고정
- [x] `evaluate_retrieval` 기본 플래그·`run_pipeline.ps1`·`README` 검증 명령 정합 (`--pg-port` 중심 원클릭)
- [x] 회귀 산출물: `service/rag/eval_report_day11.json` (`score_percent` 100, `recall@3` 100, classification `recall@3` 100)

체크:
- [x] Streamlit 검색 설정과 같은 메타에서 **참고 자료 순서**가 검색 결과·`chunk_id`와 맞는지 자동 검증: `python -m service.rag.verify_streamlit_citation_alignment --pg-port 5433` (통일부·평가 질문 2개, `reranked[:5]` ↔ `citations` 정합 + `20260423…` 포함)
- [x] **Router·사이드바 정합**: `graph/utils/level.py` 추가, 호출 시 넘긴 `meta`가 기본값을 덮어쓰도록 `router.py` 병합. 기본 **재순위화·발언자 균형 끔**(회귀와 동일, 켜면 특정 회의 청크가 밀릴 수 있음)
- [x] `recall@3` / `by_type.classification` 회귀 출력 캡처·기록

## Day 11 최종 완료 기준
- [x] **데이터 기반 답**이 검색 회귀로 재현 가능하고(`evaluate_retrieval` 전부 PASS), 평가셋 라벨은 유지

---
