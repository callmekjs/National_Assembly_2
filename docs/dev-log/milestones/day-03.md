# Day 3 - 오늘 내가 할 일 (파이프라인 안정화 + 재현성 고정)

## 목표
- [x] 같은 명령으로 ETL -> Load -> QA가 끊기지 않고 1회 완료
- [x] 실행 실패 지점이 바로 보이도록 로그/체크포인트 고정
- [x] 필수 스모크 질문 3개를 고정해 재현성 확인

## 1) 원클릭 실행 경로 정리
- [x] 실행 순서 표준화 (`run_pipeline.ps1` 기준)
- [x] 포트/환경변수 충돌 방지 (`PG_PORT=5433` 고정 확인)
- [x] 필수 선행 조건 문서화 (Docker/venv)

체크:
- [x] 새 환경에서 같은 순서로 실행 가능

## 2) 파이프라인 재실행 검증
- [x] Extract -> Transform -> Load 순차 재실행
```powershell
python -m service.etl.extractor.extractor
python -m service.etl.transform.pipeline
python -m service.etl.loader.loader_cli load doc --jsonl-dir data/transform/final
python -m service.etl.loader.loader_cli load vector
```

체크:
- [x] `chunks`/`embeddings_e5` 건수 일치 확인
- [x] 치명 오류 없이 완료

## 3) 스모크 질문 3개 고정 테스트
- [x] comparative 1개
- [x] classification 1개
- [x] 일반 요약형 1개
```powershell
python -m service.rag.qa_demo --query "외교부장관과 위원 질의자의 입장 차이를 근거와 함께 설명해줘" --top-k 20 --return-k 5 --committee "외교통일위원회" --alpha 0.75 --use-reranker --balance-speakers --pg-port 5433
python -m service.rag.qa_demo --query "외교통일위원회 회의록에서 대북정책의 실효성이 낮아진 원인을 3가지로 분석해줘" --top-k 20 --return-k 5 --committee "외교통일위원회" --alpha 0.75 --use-reranker --balance-speakers --pg-port 5433
python -m service.rag.qa_demo --query "외교통일위원회 회의록에서 대북정책 핵심 쟁점을 요약해줘" --top-k 20 --return-k 5 --committee "외교통일위원회" --alpha 0.75 --use-reranker --balance-speakers --pg-port 5433
```

체크:
- [x] 3개 모두 `Search hits >= 3`
- [x] 인용 형식 `[n] source/date/quote` 유지

## Day 3 최종 완료 기준
- [x] ETL -> Load -> QA 재실행 1회 성공
- [x] 스모크 3문항 모두 통과
- [x] 실행 실패 시 원인 파악 가능한 로그 확보

---

---
---
