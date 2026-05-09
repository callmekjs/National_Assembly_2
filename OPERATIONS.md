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
4. `streamlit run app.py` 후 **회의록 질의**에서 한 번 질의·참고 자료 확인
