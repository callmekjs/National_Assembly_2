# 운영 및 복구 (Day 8)

## 재실행 정책

- **문서 적재 (`load doc`)**: `chunks` 테이블에 `ON CONFLICT (chunk_id) DO UPDATE`로 동작합니다. 같은 JSONL을 다시 넣어도 덮어쓰기만 하며 안전합니다.
- **벡터 적재 (`load vector`)**: `embeddings_e5`에 `ON CONFLICT (chunk_id) DO UPDATE`로 동작합니다. 재실행 시 기존 임베딩이 갱신됩니다.

## 포트·환경

| 변수 | 기본값 | 권장(이 프로젝트) |
|------|--------|-------------------|
| `PG_PORT` | 5432 | **5433** (Docker 매핑) |
| `PG_HOST` | localhost | 변경 시에만 설정 |
| `PG_DB` | skn_project | 컨테이너와 일치해야 함 |

로컬에 다른 PostgreSQL이 **5432**를 쓰는 경우, `PG_PORT`를 설정하지 않으면 잘못된 DB에 붙거나 `embeddings_e5` 테이블이 없다는 오류가 납니다.

## 자주 나는 오류와 대응

1. **`connection refused` (PostgreSQL)**  
   - Docker 컨테이너가 떠 있는지 확인합니다.  
   - `PG_PORT=5433`인지 확인합니다.

2. **`relation "embeddings_e5" does not exist`**  
   - 다른 DB/포트에 연결된 경우가 많습니다. `PG_PORT`를 프로젝트 DB와 맞춥니다.  
   - 초기 스키마가 없다면 `python -m service.etl.loader.loader_cli db create` 후 다시 실행합니다.

3. **`UnicodeEncodeError` / 콘솔 깨짐 (Windows)**  
   - 실행 전 `$env:PYTHONIOENCODING='utf-8'`를 설정합니다.

4. **`db create` 실패 (docker exec)**  
   - 컨테이너 이름이 `SKN18-3rd`가 아니면 `system_manager`의 docker 실행 경로가 맞지 않을 수 있습니다. 수동으로 동일 스키마를 해당 DB에 적용해야 합니다.

## 복구 절차 (요약)

1. `PG_PORT` 확인 후 `python -m service.etl.loader.loader_cli load doc ...`  
2. `python -m service.etl.loader.loader_cli load vector`  
3. 건수 확인: `chunks`와 `embeddings_e5` 행 수가 동일한지 확인  
4. `python smoke_pipeline.py --pg-port 5433 --skip-crawl` 로 스모크

## 파이프라인 로그

`run_pipeline.ps1`은 각 단계마다 `[pipeline][단계] START/OK/FAIL` 형식으로 출력합니다.  
실패 시 단계별 힌트가 이어서 출력됩니다.

## 이중 재실행 검증

```powershell
.\run_pipeline.ps1 -PgPort 5433 -SkipCrawl -VerifyIdempotent
```

`load doc` / `load vector`를 연속 두 번 실행해 중복 적재 경로가 안정적인지 확인합니다.

## v1 출시 전 체크리스트 (Day 10)

`README.md`의 **「v1 마감 검증」** 절을 그대로 따라 하면 됩니다. 요약만 적어 둡니다.

1. Postgres + `embeddings_e5` 적재 확인  
2. `evaluate_retrieval` 1회 통과(지표는 README 참고)  
3. `qa_demo` 3문항 실행, `Search hits` 및 근거 블록 형식 확인  
4. React dev server 또는 API 엔드포인트로 **회의록 질의**에서 한 번 질의·참고 자료 확인

## LLM 생성 (Day 12 요약)

- **경로**: `.env`에 `OPENAI_API_KEY`가 있고 `FORCE_LOCAL_LLM`이 아니면 OpenAI Chat Completions 사용. 없으면 로컬 HF(`MODEL_DIR_BASE`, `MODEL_DIR_ADAPTER`).
- **환경 변수(선택)**  
  - `GENERATE_MAX_TOKENS` — Generate 노드 `max_tokens`(기본 `512`).  
  - `OPENAI_TEMPERATURE` — OpenAI만 적용(기본 `0.7`). 로컬 HF는 `llm_client`의 `generate()`에서 `temperature=0.7` 고정.  
- **재현성**: 동일 질문이라도 샘플링으로 문구가 달라질 수 있음. 더 안정적으로 쓰려면 온도·샘플링 정책을 낮추는 방향을 검토한다.
- **홈/질의 화면**: 키도 없고 로컬 모델 경로도 없으면 경고 배너가 뜬다(모델을 실제로 로드하지는 않음).

## 데이터·검색 (Day 13 요약)

- **적재 정합**: 새 배치 적재 후 `chunks` 행 수와 `embeddings_e5` 행 수가 같아야 한다. 미임베딩 행이 있으면 `python -m service.etl.loader.loader_cli load vector`로 보충한다.
- **일괄 스모크**: `python -m service.rag.smoke_day13 --pg-port 5433` — 건수 비교 + 무필터·위원회 필터·날짜 역전(자동 보정) 등 검색이 각각 `hits >= 1`인지 확인한다.
- **민감도(참고)**  
  - `committee`는 메타 JSON의 문자열과 **완전 일치**해야 한다(공백·표기 차이 시 결과 없음).  
  - `meeting_date`가 `YYYY-MM-DD`가 아니면 시작·종료 필터 문자열 비교가 어긋날 수 있다.  
  - 시작일이 종료일보다 늦게 입력되면 **`normalize_meeting_date_range`**가 순서를 바꿔 검색한다(`Retriever`·Retrieve 노드 공통).
