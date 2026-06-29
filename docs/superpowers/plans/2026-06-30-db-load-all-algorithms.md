# DB Load — 알고리즘 #1-7 메타데이터 전체 반영 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** chunker_v2.py를 재실행해 7개 알고리즘 메타데이터가 모두 담긴 JSONL을 새로 생성하고, PostgreSQL chunks_v2 테이블에 upsert, 임베딩까지 최신화한다.

**Architecture:** chunker_v2.py → chunks_v2.jsonl 재생성 → jsonl_to_postgres_v2.py upsert → qa_pairer_v2.py 재실행 → qa pairs upsert → embeddings_v2.py --force (선택). 모든 스크립트가 ON CONFLICT DO UPDATE 기반이라 기존 데이터를 덮어쓰는 방식이므로 트랜잭션 안전.

**Tech Stack:** Python, psycopg2, PostgreSQL (pgvector), JSONL

## 현황 파악 (배경)

- `data/v2/transform/final/chunks_v2.jsonl` — 2026-06-26 생성, 71,500줄
- `data/v2/transform/qa_pairs/qa_pairs_v2.jsonl` — 2026-06-27 생성 (OLD chunks 기반)
- 알고리즘 #2-7 전부 2026-06-27 커밋 → JSONL보다 최신
- DB(`chunks_v2`) 메타데이터에 누락된 필드:
  - `utterance_type_confidence` (Alg #2)
  - `issue_score` (Alg #3)
  - `importance_score` (Alg #4)
  - `meeting_phase` (Alg #7)
  - `prev_speaker`, `prev_speaker_role` (Alg #5, context window)
- turns/ 소스 데이터: 275개 폴더 존재 확인됨 → 재생성 가능

## Global Constraints

- 모든 명령은 프로젝트 루트(`C:\National_Assembly_2`)에서 실행
- v1 테이블(`chunks`, `embeddings_e5`) 절대 건드리지 않음
- ON CONFLICT DO UPDATE 사용 → 기존 청크 chunk_id는 유지, 내용만 갱신
- `section_type='body'` 청크만 임베딩 대상

---

### Task 1: chunker_v2 재실행 → chunks_v2.jsonl 재생성

**Files:**
- Modify: `data/v2/transform/final/chunks_v2.jsonl` (덮어쓰기)
- Modify: `data/v2/transform/chunks/{source_id}/chunks.jsonl` (각 소스별)

**Interfaces:**
- Consumes: `data/v2/transform/turns/*/turns.jsonl` (275개 소스)
- Produces: `data/v2/transform/final/chunks_v2.jsonl` — 모든 알고리즘 메타데이터 포함

- [ ] **Step 1: 재실행**

```powershell
cd C:\National_Assembly_2
python -m service.etl.transform.chunker_v2
```

예상 출력:
```
[chunker_v2] chunks=71500 300자미만=XXXX(XX.X%)
  → data/v2/transform/chunks/{source_id}/chunks.jsonl
  → data/v2/transform/final/chunks_v2.jsonl (merged)
```

- [ ] **Step 2: 라인 수 검증**

```powershell
(Get-Content "data\v2\transform\final\chunks_v2.jsonl" | Measure-Object -Line).Lines
```

기존과 유사한 수(~71,500) 나오면 OK. 크게 달라지면 원인 확인.

- [ ] **Step 3: 신규 메타데이터 필드 spot-check**

```powershell
$sample = Get-Content "data\v2\transform\final\chunks_v2.jsonl" -TotalCount 200
# 200번째 줄(첫 speaker가 있는 body 청크 근처) 확인
# utterance_type_confidence, issue_score, importance_score, meeting_phase가 있어야 함
```

아래 Python 스크립트로 확인:

```python
# C:\National_Assembly_2\scripts\check_jsonl_meta.py (임시)
import json
from pathlib import Path

path = Path("data/v2/transform/final/chunks_v2.jsonl")
required_keys = [
    "utterance_type", "utterance_type_confidence",
    "issue_score", "importance_score", "meeting_phase",
    "question_type_hints", "agency",
]
found = 0
for line in path.open(encoding="utf-8"):
    d = json.loads(line)
    meta = d.get("metadata", {})
    if d.get("speaker"):  # speaker 있는 청크만
        missing = [k for k in required_keys if k not in meta]
        if missing:
            print(f"MISSING {missing} in {d['chunk_id']}")
        else:
            found += 1
        if found >= 5:
            print("OK: 첫 5개 speaker 청크 모두 필드 확인됨")
            break
```

```powershell
python scripts\check_jsonl_meta.py
```

예상: `OK: 첫 5개 speaker 청크 모두 필드 확인됨`

- [ ] **Step 4: 커밋**

```powershell
git add data/v2/transform/final/chunks_v2.jsonl
git commit -m "data: chunks_v2.jsonl 재생성 — 알고리즘 #2-7 메타데이터 포함"
```

---

### Task 2: chunks_v2 DB upsert

**Files:**
- Reads: `data/v2/transform/final/chunks_v2.jsonl`
- Writes: PostgreSQL `chunks_v2` 테이블

**Interfaces:**
- Consumes: Task 1에서 생성된 `chunks_v2.jsonl`
- Produces: `chunks_v2` 테이블에 71,500행 upsert (chunk_id 충돌 시 모든 컬럼 갱신)

- [ ] **Step 1: upsert 실행**

```powershell
python -m service.etl.loader.jsonl_to_postgres_v2
```

예상 출력:
```
[loader_v2] upsert_rows=71500 → chunks_v2
[loader_v2] QA 쌍 파일 없음 (스킵): ...  ← qa_pairs 아직 안 됐으면 스킵됨
```

에러나면 `[loader_v2] ERROR: ...` 출력. PostgreSQL 연결 안 되면 `.env` 확인.

- [ ] **Step 2: DB 행 수 검증**

```powershell
# psql로 직접 확인 (또는 pgAdmin)
# 아래 SQL 실행:
# SELECT COUNT(*) FROM chunks_v2;
# SELECT COUNT(*) FROM chunks_v2 WHERE section_type = 'body';
```

또는 Python으로:

```python
# scripts\verify_db.py (임시)
import os, psycopg2
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path("../.env") if not Path(".env").exists() else Path(".env"))

conn = psycopg2.connect(
    host=os.getenv("PG_HOST", "localhost"),
    port=int(os.getenv("PG_PORT", "5432")),
    database=os.getenv("PG_DB", "skn_project"),
    user=os.getenv("PG_USER", "postgres"),
    password=os.getenv("PG_PASSWORD", "post1234"),
)
with conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM chunks_v2")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM chunks_v2 WHERE section_type = 'body'")
    body = cur.fetchone()[0]
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE metadata->>'utterance_type_confidence' IS NOT NULL) AS has_confidence,
            COUNT(*) FILTER (WHERE metadata->>'issue_score' IS NOT NULL) AS has_issue,
            COUNT(*) FILTER (WHERE metadata->>'importance_score' IS NOT NULL) AS has_importance,
            COUNT(*) FILTER (WHERE metadata->>'meeting_phase' IS NOT NULL) AS has_phase
        FROM chunks_v2 WHERE section_type = 'body'
    """)
    row = cur.fetchone()
    print(f"total={total}, body={body}")
    print(f"confidence={row[0]}, issue={row[1]}, importance={row[2]}, phase={row[3]}")
conn.close()
```

```powershell
python scripts\verify_db.py
```

예상: confidence/issue/importance/phase 모두 body 행 수와 동일하면 OK.

---

### Task 3: qa_pairer 재실행 → qa_pairs DB upsert

**Files:**
- Reads: `data/v2/transform/final/chunks_v2.jsonl` (Task 1 결과)
- Writes: `data/v2/transform/qa_pairs/qa_pairs_v2.jsonl`
- Writes: PostgreSQL `chunks_v2` 테이블 (section_type='body', chunk_type='qa_pair')

**Interfaces:**
- Consumes: Task 1 새 JSONL (utterance_type_confidence 필드 포함)
- Produces: qa pair 레코드 (chunk_id `{source_id}_qa_{N:04d}` 형식)

- [ ] **Step 1: qa_pairer 재실행**

```powershell
python -m service.etl.transform.qa_pairer_v2
```

예상 출력 예시:
```
[qa_pairer] source=20240611_52074_52074 pairs=12
...
[qa_pairer] total_pairs=XXXX → data/v2/transform/qa_pairs/qa_pairs_v2.jsonl
```

- [ ] **Step 2: QA pairs DB upsert**

```python
# scripts\load_qa.py (임시)
from service.etl.loader.jsonl_to_postgres_v2 import load_qa_pairs
load_qa_pairs()
```

```powershell
python scripts\load_qa.py
```

예상 출력:
```
[loader_v2] upsert_rows=XXXX → chunks_v2
```

- [ ] **Step 3: QA pair 행 수 검증**

```python
# scripts\verify_db.py에 추가하거나 별도 실행
with conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM chunks_v2 WHERE metadata->>'chunk_type' = 'qa_pair'")
    qa_count = cur.fetchone()[0]
    print(f"qa_pairs={qa_count}")
```

- [ ] **Step 4: 커밋**

```powershell
git add data/v2/transform/qa_pairs/qa_pairs_v2.jsonl
git commit -m "data: qa_pairs_v2.jsonl 재생성 — 신규 chunks 기반 (utterance_type_confidence 반영)"
```

---

### Task 4: 임베딩 최신화 (embeddings_e5_v2)

**배경:** embed_text는 `utterance_type` 포함 → Algorithm #2에서 ~139개 청크의 utterance_type이 question→statement로 바뀜. 기존 임베딩은 그 변경 전 embed_text 기반. 대부분(99.8%) 청크는 embed_text 동일.

**선택지:**
- **Option A (권장)**: 전체 재임베딩. 정확하지만 오래 걸림 (~1-2시간, GPU 환경 따라 다름)
- **Option B (빠름)**: 건너뜀. 메타데이터만 반영되고 임베딩은 현재 상태 유지. retrieval 점수는 issue_score/importance_score로 이미 개선됨.

**Files:**
- Writes: PostgreSQL `embeddings_e5_v2` 테이블

- [ ] **Step 1: 현재 임베딩 행 수 확인**

```python
with conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM embeddings_e5_v2")
    emb_count = cur.fetchone()[0]
    print(f"embeddings={emb_count}")
```

임베딩이 0이면 신규 로드 필요. 71,500 근방이면 Option B 선택 가능.

- [ ] **Step 2-A: [Option A] 전체 재임베딩**

```powershell
# 먼저 기존 임베딩 삭제 (truncate가 더 빠름)
# psql: TRUNCATE TABLE embeddings_e5_v2;
# 또는:
python -c "
import os, psycopg2
from dotenv import load_dotenv; load_dotenv('.env')
conn = psycopg2.connect(host=os.getenv('PG_HOST','localhost'), port=int(os.getenv('PG_PORT','5432')), database=os.getenv('PG_DB','skn_project'), user=os.getenv('PG_USER','postgres'), password=os.getenv('PG_PASSWORD','post1234'))
conn.autocommit = True
with conn.cursor() as cur: cur.execute('TRUNCATE TABLE embeddings_e5_v2')
conn.close()
print('truncated')
"

# 전체 재임베딩 (시간 많이 걸림)
python -m service.etl.loader.embeddings_v2 --batch-size 100
```

예상 출력:
```
[embed_v2] 신규 청크만 | 대상: 71500개
[embed_v2] batch 1: upsert=100
...
[embed_v2] done total_embedded=71500
```

- [ ] **Step 2-B: [Option B] 임베딩 스킵**

Option B 선택 시 이 Task 4 전체를 건너뛴다. 추후 필요 시 `--force` 옵션으로 재실행 가능.

---

### Task 5: 최종 검증 및 정리

**Files:**
- Delete: `scripts/check_jsonl_meta.py`, `scripts/verify_db.py`, `scripts/load_qa.py` (임시 스크립트 삭제)

- [ ] **Step 1: 검색 동작 spot-test**

```python
# 로컬에서 retriever.search_v2 테스트
from service.rag.retrieval.retriever import search_v2

results = search_v2("환경부 장관 미세먼지 답변", limit=3)
for r in results:
    meta = r.get("metadata", {})
    print(r["chunk_id"], meta.get("issue_score"), meta.get("importance_score"), meta.get("meeting_phase"))
```

예상: 결과 3개 출력, `issue_score`/`importance_score`/`meeting_phase`가 None이 아닌 실수값으로 나오면 OK.

- [ ] **Step 2: 임시 스크립트 삭제**

```powershell
Remove-Item scripts\check_jsonl_meta.py -ErrorAction SilentlyContinue
Remove-Item scripts\verify_db.py -ErrorAction SilentlyContinue
Remove-Item scripts\load_qa.py -ErrorAction SilentlyContinue
```

- [ ] **Step 3: 메모리 업데이트**

DB 로드 완료 후 project_algorithm_series.md 메모리의 "DB 로드 미완료" 상태를 "DB 로드 완료"로 갱신.

- [ ] **Step 4: 최종 커밋**

```powershell
git add -A
git commit -m "feat: DB load 완료 — 알고리즘 #1-7 메타데이터 chunks_v2 전체 반영"
```
