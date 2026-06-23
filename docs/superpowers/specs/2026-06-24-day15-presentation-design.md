---
title: Day 15 발표·포트폴리오 마감 설계
date: 2026-06-24
status: approved
---

# Day 15 발표·포트폴리오 마감 설계

## 목표

발표·면접·포트폴리오 제출에 바로 쓸 수 있는 패키지를 한 파일로 완성한다.
`docs/presentation/day15-package.md` 한 파일에 서사·데모·다이어그램·수치를 모두 담는다.

---

## 파일 구조

| 파일 | 상태 | 내용 |
|------|------|------|
| `docs/presentation/day15-package.md` | 신규 | 60초 서사 + 데모 스크립트 + Mermaid 다이어그램 + 수치 스냅샷 |
| `docs/dev-log/milestones/day-15.md` | 수정 | 완성된 마일스톤 체크리스트 (day15-package.md 링크 포함) |

---

## day15-package.md 섹션 설계

### 섹션 1: 60초 서사

포트폴리오·면접용 구어체 스크립트. 3문장 구조:
1. **데이터**: 국회 외교통일위원회 회의록 55건, 발언자 단위 18,048개 청크를 PostgreSQL + pgvector에 적재
2. **기능**: 질문 입력 → 하이브리드 검색(벡터+키워드+리랭크) → LLM이 `[1][2]` 출처 인용과 함께 답변
3. **증거**: recall@3 100%, RAGAS faithfulness 0.9857, 할루시네이션 방어 전 케이스 PASS

### 섹션 2: 데모 질문 3개 + 실패 대사

**순서 고정 (비교 → 분류 → 요약):**

| 유형 | 질문 | 기대 출력 패턴 |
|------|------|----------------|
| 비교 | "조태열 장관과 정동영 의원의 대북정책 입장 차이를 비교해줘" | 발언자별 대조 + `[1][2]` 인용 |
| 분류 | "통일부 장관이 북한 인권에 대해 어떤 입장이야?" | 특정 발언자 발언 + 근거 청크 |
| 요약 | "최근 북핵 비핵화 논의를 요약해줘" | 다수 발언자 종합 + 한계 명시 |

**실패 시 대사 (각 1줄):**
- DB 미기동: "docker-compose up -d 먼저 실행 후 python scripts/healthcheck.py로 확인합니다"
- 모델 파일 없음: "models/ 경로에 LLaMA 베이스 모델이 필요합니다. .env의 MODEL_DIR_BASE를 확인하세요"
- OpenAI 키 없음: "OPENAI_API_KEY 미설정 시 로컬 HF 모델 폴백으로 답변 품질이 낮아질 수 있습니다"

### 섹션 3: Mermaid 아키텍처 다이어그램

두 레이어를 한 다이어그램으로:
- **[메인] 사용자 흐름**: Streamlit → LangGraph → 하이브리드 검색 → LLM 생성 → 출처 인용 답변
- **[전제] ETL 파이프라인**: 원문 → Extract → Transform(정규화·청킹) → Load → Postgres + pgvector

```mermaid
flowchart TD
    subgraph USER["[메인] 사용자 흐름"]
        A[사용자 질문] --> B[Streamlit UI]
        B --> C[LangGraph 파이프라인]
        C --> D[하이브리드 검색\n벡터+키워드+리랭크]
        D --> E[(PostgreSQL\npgvector)]
        C --> F[LLM 생성\nGPT-4o-mini]
        F --> G[출처 인용 답변\n[1][2] + Grounding Check]
    end
    subgraph ETL["[전제] ETL 파이프라인"]
        H[국회 회의록 원문\n55건] --> I[Extract\n파싱·정규화]
        I --> J[Transform\n발언자 단위 청킹\n18,048개]
        J --> K[Load\n문서·임베딩 적재]
        K --> E
    end
```

### 섹션 4: 핵심 수치 스냅샷

EVALUATION.md (2026-06-22 기준) 핵심 지표 5개:

| 지표 | 수치 |
|------|------|
| 데이터 | 외교통일위원회 회의록 55건 · 청크 18,048개 |
| recall@3 | **100%** (10/10, 비교·분류·요약 전 유형) |
| RAGAS faithfulness | **0.9857** |
| 할루시네이션 방어 | 전 케이스 PASS (인물 날조·허구 문서·수치 날조 등 24개) |
| Grounding Check | FULL / PARTIAL / NONE 3단계, 전 케이스 PASS |

---

## day-15.md 완성 내용

기존 체크리스트를 완료 상태로 교체:
- [x] 60초 서사 (`docs/presentation/day15-package.md`)
- [x] 데모 질문 3개 스크립트 (비교·분류·요약) + 실패 대사
- [x] 아키텍처 다이어그램 (Mermaid, `day15-package.md` 포함)
- [x] EVALUATION.md 수치 스냅샷 확인 (2026-06-22 기준, 최신)
- [x] `docs/dev-log/milestones/day-15.md` 완성

---

## 성공 기준

1. `docs/presentation/day15-package.md` 존재, 4개 섹션 모두 포함
2. Mermaid 코드블록이 `flowchart TD`로 시작하고 두 subgraph 포함
3. 데모 질문 3개(비교·분류·요약)와 실패 대사 3개 포함
4. `docs/dev-log/milestones/day-15.md` 전체 항목 [x] 체크
