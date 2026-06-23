# Day 2 - 오늘 내가 할 일 (검색 품질 개선 + QA 안정화)

## 목표 (초기 수치 목표 — 이후 Day 6·10 회귀에서 초과 달성)
- [x] 정답기반 평가 점수 `60% -> 75%+`로 개선
- [x] `Recall@3`를 `20% -> 40%+`로 개선
- [x] QA 데모에서 근거 인용 형식 일관성 확인

## 1) 평가 기준선 재확인
- [x] 기존 평가 재실행
```powershell
python -m service.rag.evaluate
```

체크:
- [x] `score / recall@3 / mrr@3` 현재 값 기록
- [x] 실패 케이스(오답 질문) 3개 이상 추출

## 2) Transform 품질 보강 (청크/정규화)
- [x] 청크 길이, overlap, 문장 경계 설정 점검
- [x] 메타데이터 누락(`committee`, `meeting_date`, `speaker`) 케이스 보강
- [x] 전처리 후 Transform 재실행
```powershell
python -m service.etl.transform.pipeline
```

체크:
- [x] `data/transform/final/chunks.jsonl` 생성 확인
- [x] 샘플 5개를 눈으로 확인해 문맥 단절 여부 체크

## 3) Load 재적재 + 벡터 재생성
- [x] DB/벡터 로드 재실행
```powershell
python -m service.etl.loader.loader_cli load doc --jsonl-dir data/transform/final
python -m service.etl.loader.loader_cli load vector
```

체크:
- [x] 오류 없이 종료되는지 확인
- [x] 재적재 후 검색 결과 상위 3개 품질 확인

## 4) Retrieval/Filter 튜닝
- [x] `top_k`, 유사도 cutoff, 메타 필터 기본값 조정
- [x] 질문 유형별(정책/인물/일정) 검색 결과 비교
- [x] 필터 검색 (`committee`, `date_from`, `date_to`) 회귀 점검

체크:
- [x] 질문 10개 중 7개 이상에서 관련 문서 hit 확인

## 5) QA 데모 답변 품질 점검
- [x] QA 데모 실행
```powershell
python -m service.rag.qa_demo
```

체크:
- [x] 인용 형식(`[n] source/date/quote`) 유지 확인
- [x] 답변과 인용 근거의 의미 일치 여부 점검

## 최종 완료 기준
- [x] 정답기반 score 75%+ (Day 10 회귀 기준 `score_percent` 약 90% 수준으로 충족)
- [x] recall@3 40%+ (`recall@3` 약 80% 수준으로 충족)
- [x] mrr@3 개선(기준선 대비 상승)
- [x] QA 답변 5개 수동 점검 시 인용 오류 0건

---
