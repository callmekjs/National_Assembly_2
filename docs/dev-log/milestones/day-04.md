# Day 4 - 오늘 내가 할 일 (데모 완성 + v0 고정)

> **메인 데모 정의**: 사용자 입장의 핵심은 **Streamlit에서 LLM이 만든 답변 + 참고 자료**까지다. 파이프라인은 그전에 끝나 있어야 하는 **전제 작업**이다.

## 목표
- [x] Streamlit에서 질문 → 검색 → **LLM 답변** → 인용(참고 자료)까지 데모 가능
- [x] 팀원이 문서만 보고 재현 가능한 상태(v0)로 고정
- [x] 최소 운영 체크리스트 작성 (`README`, `OPERATIONS.md`)

## 1) UI 데모 흐름 점검
- [x] Streamlit 실행
```powershell
streamlit run app.py
```

체크:
- [x] 질문 입력/응답 출력 정상 (`Day 9·10` UX·회귀 반영)
- [x] 인용 근거 표시 정상 (답변 하단 `[n] source/date/quote`)
- [x] 오류 시 사용자 메시지 깨지지 않음

## 2) v0 실행 가이드 고정
- [x] README 실행 순서 5줄 요약
- [x] 필수 환경변수/포트 명시 (Streamlit·LLM 경로 vs `qa_demo` 구분 포함, `Day 10` 반영)
- [x] 자주 나는 오류와 해결 3개 정리

체크:
- [x] 처음 보는 사람도 문서만으로 실행 가능 (`README` v1 검증 절 + `OPERATIONS.md`)

## 3) 최종 회귀 1회
- [x] retrieval 평가 1회
```powershell
python -m service.rag.evaluate_retrieval --top-k 3 --pg-port 5433
```
- [x] QA 데모 1회
```powershell
python -m service.rag.qa_demo --query "대북정책 핵심 쟁점을 요약해줘" --top-k 20 --return-k 5 --committee "외교통일위원회" --alpha 0.75 --use-reranker --balance-speakers --pg-port 5433
```

체크:
- [x] 평가/데모가 모두 오류 없이 종료
- [x] 답변 인용 형식 유지

## Day 4 최종 완료 기준
- [x] UI 데모 시나리오 1회 성공 (근거 기반 **LLM** 답변 포함)
- [x] README 기준 재현 테스트 1회 성공 (`Day 10` 회귀 명령 정리)
- [x] v0 릴리즈 기준(실행 가능/근거 표시/오류 대응) 충족

---

---
---
