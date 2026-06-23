# Day 14 배포·재현성 패키징 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `git clone → docker-compose up → streamlit run app.py` 3단계로 누구나 실행할 수 있도록 헬스 체크 CLI, README 표, 원데이 검증 노트를 완성한다.

**Architecture:** `scripts/healthcheck.py`는 `.env` 자동 로드 + argparse CLI로 Postgres 4단계 진단을 수행한다. README에 서비스 구성 표와 헬스 체크 단계를 추가한다. `docs/dev-log/milestones/day-14.md`를 완성된 원데이 검증 노트로 교체한다.

**Tech Stack:** Python 3.10+, psycopg2-binary, pgvector, python-dotenv, pytest

## Global Constraints

- Python CLI: `python scripts/healthcheck.py` (옵션 없이 `.env` 사용, `--pg-port` 등으로 오버라이드)
- 4단계 체크 순서: Postgres 연결 → chunks 수 → embeddings_e5 수 → 벡터 차원 384
- 실패 시 `sys.exit(1)`, 성공 시 `sys.exit(0)`
- 출력 접두어: `[✅]` 성공, `[❌]` 실패, `[⏭️]` 이전 단계 실패로 건너뜀
- 단계 실패 시 이후 단계는 SKIP하고 즉시 종료
- `python-dotenv`로 프로젝트 루트 `.env` 자동 로드 (없으면 무시)
- CLI 인자 > 환경변수 > 기본값 우선순위
- 기본값: host=localhost, port=5432, db=skn_project, user=postgres, password=post1234

---

## File Map

| 파일 | 상태 | 역할 |
|------|------|------|
| `scripts/healthcheck.py` | 신규 | 4단계 Postgres 진단 CLI |
| `tests/test_healthcheck.py` | 신규 | subprocess로 CLI exit code + 출력 검증 |
| `README.md` | 수정 | 서비스 구성 표 섹션 + 헬스 체크 단계 추가 |
| `docs/dev-log/milestones/day-14.md` | 수정 | 원데이 검증 노트로 완성 |

---

### Task 1: scripts/healthcheck.py + 테스트

**Files:**
- Create: `scripts/healthcheck.py`
- Create: `tests/test_healthcheck.py`

**Interfaces:**
- Produces: `python scripts/healthcheck.py [--pg-host H] [--pg-port P] [--pg-db D] [--pg-user U] [--pg-password PW]` → stdout 4단계 결과, exit 0/1

- [ ] **Step 1: 테스트 파일 작성**

`tests/test_healthcheck.py` 전체 내용:

```python
"""
scripts/healthcheck.py CLI 테스트 (실제 DB 필요: PG_PORT=5433)

실행:
  pytest tests/test_healthcheck.py -v --pg-port 5433
"""
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])


class TestHealthcheck:

    def test_success_with_real_db(self, pg_port):
        """실제 DB에서 4단계 모두 통과."""
        result = subprocess.run(
            [sys.executable, "scripts/healthcheck.py", "--pg-port", str(pg_port)],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        assert result.returncode == 0, f"exit 1:\n{result.stdout}\n{result.stderr}"
        assert "모든 헬스 체크 통과" in result.stdout
        assert "[✅] Postgres 연결" in result.stdout
        assert "[✅] chunks 테이블" in result.stdout
        assert "[✅] embeddings_e5 테이블" in result.stdout
        assert "[✅] 벡터 차원: 384" in result.stdout

    def test_failure_on_bad_port(self):
        """존재하지 않는 포트 → exit 1 + 연결 실패 메시지."""
        result = subprocess.run(
            [sys.executable, "scripts/healthcheck.py", "--pg-port", "9999"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        assert result.returncode == 1
        assert "[❌] Postgres 연결 실패" in result.stdout
        assert "헬스 체크 실패" in result.stdout

    def test_skip_shown_on_connection_failure(self):
        """연결 실패 시 이후 단계는 ⏭️ 없이 종료 (연결 단계에서 즉시 종료)."""
        result = subprocess.run(
            [sys.executable, "scripts/healthcheck.py", "--pg-port", "9999"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        assert result.returncode == 1
        # 연결 실패 시 chunks/embeddings 체크는 아예 출력되지 않음
        assert "chunks 테이블" not in result.stdout
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```powershell
cd C:\National_Assembly_2
pytest tests/test_healthcheck.py -v --pg-port 5433
```

Expected: `FAILED` (scripts/healthcheck.py 없음)

- [ ] **Step 3: scripts/healthcheck.py 작성**

먼저 `scripts/` 디렉토리를 생성하고, `scripts/healthcheck.py` 전체 내용:

```python
#!/usr/bin/env python3
"""
헬스 체크 CLI — Postgres + pgvector 데이터 존재 여부 확인

실행:
  python scripts/healthcheck.py
  python scripts/healthcheck.py --pg-port 5433
"""
import argparse
import json
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass


def _get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Postgres + pgvector 헬스 체크")
    parser.add_argument("--pg-host", default=os.environ.get("PG_HOST", "localhost"))
    parser.add_argument("--pg-port", type=int, default=int(os.environ.get("PG_PORT", "5432")))
    parser.add_argument("--pg-db", default=os.environ.get("PG_DB", "skn_project"))
    parser.add_argument("--pg-user", default=os.environ.get("PG_USER", "postgres"))
    parser.add_argument("--pg-password", default=os.environ.get("PG_PASSWORD", "post1234"))
    return parser.parse_args()


def _ok(msg: str) -> None:
    print(f"[✅] {msg}")


def _fail(msg: str) -> None:
    print(f"[❌] {msg}")


def _skip(msg: str) -> None:
    print(f"[⏭️] {msg} (이전 단계 실패로 건너뜀)")


def main() -> int:
    args = _get_args()
    conn_str = f"{args.pg_host}:{args.pg_port}/{args.pg_db}"

    # Step 1: Postgres 연결
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=args.pg_host,
            port=args.pg_port,
            database=args.pg_db,
            user=args.pg_user,
            password=args.pg_password,
        )
        _ok(f"Postgres 연결 ({conn_str})")
    except Exception as exc:
        _fail(f"Postgres 연결 실패: {exc}")
        print("\n헬스 체크 실패 — 위 항목을 확인하세요.")
        return 1

    # Step 2: chunks 테이블
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM chunks")
            count = int(cur.fetchone()[0])
        if count == 0:
            _fail("chunks 테이블: 0건 (데이터 없음)")
            _skip("embeddings_e5 테이블")
            _skip("벡터 차원")
            print("\n헬스 체크 실패 — 위 항목을 확인하세요.")
            conn.close()
            return 1
        _ok(f"chunks 테이블: {count:,}건")
    except Exception as exc:
        _fail(f"chunks 테이블 조회 실패: {exc}")
        _skip("embeddings_e5 테이블")
        _skip("벡터 차원")
        print("\n헬스 체크 실패 — 위 항목을 확인하세요.")
        conn.close()
        return 1

    # Step 3: embeddings_e5 테이블
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM embeddings_e5")
            count = int(cur.fetchone()[0])
        if count == 0:
            _fail("embeddings_e5 테이블: 0건 (임베딩 없음)")
            _skip("벡터 차원")
            print("\n헬스 체크 실패 — 위 항목을 확인하세요.")
            conn.close()
            return 1
        _ok(f"embeddings_e5 테이블: {count:,}건")
    except Exception as exc:
        _fail(f"embeddings_e5 테이블 조회 실패: {exc}")
        _skip("벡터 차원")
        print("\n헬스 체크 실패 — 위 항목을 확인하세요.")
        conn.close()
        return 1

    # Step 4: 벡터 차원
    try:
        try:
            from pgvector.psycopg2 import register_vector
            register_vector(conn)
        except Exception:
            pass
        with conn.cursor() as cur:
            cur.execute("SELECT embedding FROM embeddings_e5 LIMIT 1")
            row = cur.fetchone()
        if row is None:
            _fail("벡터 차원 확인 실패: 레코드 없음")
            print("\n헬스 체크 실패 — 위 항목을 확인하세요.")
            conn.close()
            return 1
        emb = row[0]
        if isinstance(emb, str):
            emb = json.loads(emb)
        dim = len(list(emb))
        if dim != 384:
            _fail(f"벡터 차원 불일치: {dim} (기대값 384)")
            print("\n헬스 체크 실패 — 위 항목을 확인하세요.")
            conn.close()
            return 1
        _ok(f"벡터 차원: {dim}")
    except Exception as exc:
        _fail(f"벡터 차원 확인 실패: {exc}")
        print("\n헬스 체크 실패 — 위 항목을 확인하세요.")
        conn.close()
        return 1

    conn.close()
    print("\n모든 헬스 체크 통과 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```powershell
pytest tests/test_healthcheck.py -v --pg-port 5433
```

Expected:
```
tests/test_healthcheck.py::TestHealthcheck::test_success_with_real_db PASSED
tests/test_healthcheck.py::TestHealthcheck::test_failure_on_bad_port PASSED
tests/test_healthcheck.py::TestHealthcheck::test_skip_shown_on_connection_failure PASSED
3 passed
```

- [ ] **Step 5: 기존 테스트 회귀 확인**

```powershell
pytest tests/ -v --pg-port 5433 2>&1 | tail -5
```

Expected: 전부 PASSED (49/49)

- [ ] **Step 6: 커밋**

```bash
git add scripts/healthcheck.py tests/test_healthcheck.py
git commit -m "feat: Postgres 헬스 체크 CLI 추가 (scripts/healthcheck.py)"
```

---

### Task 2: README.md 서비스 구성 표 + 헬스 체크 단계 추가

**Files:**
- Modify: `README.md` (line 201 근처 — `---` 다음, `## 빠른 시작` 이전에 섹션 삽입)
- Modify: `README.md` (line 224 근처 — `### 2. DB 기동` 블록 아래에 헬스 체크 substep 추가)

**Interfaces:**
- Consumes: 없음 (독립 문서 변경)
- Produces: 없음 (문서 변경)

- [ ] **Step 1: 서비스 구성 섹션 삽입**

`README.md`에서 아래 텍스트를 찾아:
```
---

## 빠른 시작
```

다음 내용으로 교체 (섹션 삽입):
```markdown
---

## 서비스 구성

| 서비스   | 포트  | 볼륨           | 설명                       |
|---------|-------|----------------|----------------------------|
| postgres | 5432  | postgres_data  | PostgreSQL + pgvector DB   |
| (앱)     | 8501  | —              | Streamlit (로컬 직접 실행) |

> **포트 충돌 시** `.env`에서 `PG_PORT=5433`으로 변경 후 `docker-compose up -d` 재실행.

---

## 빠른 시작
```

- [ ] **Step 2: 헬스 체크 substep 삽입**

`README.md`에서 아래 텍스트를 찾아:
```
### 2. DB 기동 (PostgreSQL + pgvector)

```powershell
docker-compose up -d
```

### 3. 데이터 파이프라인 실행
```

다음 내용으로 교체 (헬스 체크 substep 삽입):
```markdown
### 2. DB 기동 (PostgreSQL + pgvector)

```powershell
docker-compose up -d
```

DB 기동 후 정상 여부 확인:

```powershell
python scripts/healthcheck.py
```

정상 출력:
```
[✅] Postgres 연결 (localhost:5432/skn_project)
[✅] chunks 테이블: 18,048건
[✅] embeddings_e5 테이블: 17,xxx건
[✅] 벡터 차원: 384

모든 헬스 체크 통과 ✅
```

### 3. 데이터 파이프라인 실행
```

- [ ] **Step 3: 변경 확인**

```powershell
python -c "
content = open('README.md', encoding='utf-8').read()
assert '## 서비스 구성' in content, '서비스 구성 섹션 없음'
assert 'postgres_data' in content, '볼륨 표 없음'
assert 'python scripts/healthcheck.py' in content, '헬스 체크 명령 없음'
assert '모든 헬스 체크 통과' in content, '기대 출력 없음'
print('README 검증 통과')
"
```

Expected: `README 검증 통과`

- [ ] **Step 4: 커밋**

```bash
git add README.md
git commit -m "docs: README에 서비스 구성 표 및 헬스 체크 단계 추가"
```

---

### Task 3: docs/dev-log/milestones/day-14.md 원데이 검증 노트 완성

**Files:**
- Modify: `docs/dev-log/milestones/day-14.md` (전체 교체)

**Interfaces:**
- Consumes: 없음
- Produces: 없음 (문서 변경)

- [ ] **Step 1: day-14.md 전체 교체**

`docs/dev-log/milestones/day-14.md`를 아래 내용으로 완전히 교체:

```markdown
# Day 14 — 배포·재현성 패키징

> 완료일: 2026-06-24  
> 목표: 외부인이 `git clone` 후 당일 내에 시스템을 실행할 수 있는 환경 구성

---

## 완료 항목

- [x] `docker-compose.yml` — PostgreSQL + pgvector 서비스 정의 (포트 5432, 볼륨 postgres_data)
- [x] `.env.example` — PG, HuggingFace, OpenAI 환경변수 템플릿 제공
- [x] `scripts/healthcheck.py` — Postgres 연결·데이터 존재 4단계 진단 CLI
- [x] README 서비스 구성 표 추가 (서비스·포트·볼륨)
- [x] README 빠른 시작에 헬스 체크 단계 추가

---

## 원데이 검증 노트 (신규 머신 기준)

### 전제 조건

| 항목 | 설치 방법 |
|------|-----------|
| Python 3.10+ | https://python.org |
| Docker Desktop | https://docker.com |
| Git | https://git-scm.com |

모델 파일 (로컬 보유 필요):
- `models/base/Llama-3.2-3B` (약 6 GB)
- `models/adapters/Llama-3.2-3B-ko-finetuned` (약 100 MB)

### 단계별 실행 순서

**1단계: 클론 및 의존성 설치**
```powershell
git clone https://github.com/callmekjs/National_Assembly_2.git
cd National_Assembly_2
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**2단계: 환경변수 설정**
```powershell
cp .env.example .env
# .env 열어서 OPENAI_API_KEY, PG_PORT 등 실제 값으로 수정
```

**3단계: DB 기동**
```powershell
docker-compose up -d
```

**4단계: DB 헬스 체크**
```powershell
python scripts/healthcheck.py
# 모든 헬스 체크 통과 ✅ 출력 확인
```

데이터가 없는 신규 환경이라면 chunks·embeddings 0건으로 실패할 수 있음 → 5단계로 계속

**5단계: 데이터 파이프라인 실행 (신규 환경 전용)**
```powershell
.\run_pipeline.ps1 -PgPort 5432
# 완료 후 python scripts/healthcheck.py 재실행
```

**6단계: Streamlit 앱 실행**
```powershell
streamlit run app.py
# http://localhost:8501 접속
```

---

## 자주 묻는 문제

| 증상 | 원인 | 해결 |
|------|------|------|
| `Postgres 연결 실패 (port 5432)` | Docker 미기동 또는 포트 충돌 | `docker-compose up -d` 재실행, 충돌 시 `.env`에서 `PG_PORT=5433` 변경 |
| `chunks 테이블: 0건` | 데이터 파이프라인 미실행 | `run_pipeline.ps1` 실행 |
| `embeddings_e5 테이블: 0건` | 임베딩 로딩 미완료 | `python -m service.etl.loader.loader_cli load vector` 실행 |
| 모델 파일 없음 오류 | `MODEL_DIR_BASE` 경로 미설정 | `.env`에서 `MODEL_DIR_BASE`, `MODEL_DIR_ADAPTER` 경로 확인 |
```

- [ ] **Step 2: 내용 검증**

```powershell
python -c "
content = open('docs/dev-log/milestones/day-14.md', encoding='utf-8').read()
assert '원데이 검증 노트' in content, '검증 노트 없음'
assert 'scripts/healthcheck.py' in content, '헬스 체크 명령 없음'
assert '자주 묻는 문제' in content, 'FAQ 없음'
assert '완료 항목' in content, '완료 항목 없음'
print('day-14.md 검증 통과')
"
```

Expected: `day-14.md 검증 통과`

- [ ] **Step 3: 커밋**

```bash
git add docs/dev-log/milestones/day-14.md
git commit -m "docs: day-14 원데이 검증 노트 완성"
```
