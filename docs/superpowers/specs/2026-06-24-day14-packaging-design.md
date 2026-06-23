---
title: Day 14 배포·재현성 패키징 설계
date: 2026-06-24
status: approved
---

# Day 14 배포·재현성 패키징 설계

## 목표

외부인이 `git clone → docker-compose up → streamlit run app.py` 3단계로 프로젝트를 실행할 수 있도록 문서와 도구를 정비한다.

---

## 범위

| 항목 | 내용 |
|------|------|
| `scripts/healthcheck.py` | 신규 — Postgres 연결 + 데이터 존재 여부 4단계 진단 CLI |
| `docker-compose.yml` | 유지 — postgres 서비스만, 변경 없음 |
| `README.md` | 수정 — 서비스·포트·볼륨 표 + 시작 순서 섹션 추가 |
| `docs/dev-log/milestones/day-14.md` | 수정 — 원데이 검증 노트로 완성 |

---

## scripts/healthcheck.py 설계

### 실행 방법

```powershell
python scripts/healthcheck.py                  # .env 파일 자동 로드
python scripts/healthcheck.py --pg-port 5433   # 포트 오버라이드
```

### CLI 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--pg-host` | `PG_HOST` env 또는 `localhost` | DB 호스트 |
| `--pg-port` | `PG_PORT` env 또는 `5432` | DB 포트 |
| `--pg-db` | `PG_DB` env 또는 `skn_project` | DB 이름 |
| `--pg-user` | `PG_USER` env 또는 `postgres` | DB 유저 |
| `--pg-password` | `PG_PASSWORD` env 또는 `post1234` | DB 비밀번호 |

- `python-dotenv`로 `.env` 파일 자동 로드 (있으면)
- CLI 인자가 환경변수보다 우선

### 4단계 체크

| 단계 | 검증 내용 | 실패 조건 |
|------|-----------|-----------|
| 1 | Postgres 연결 | psycopg2 연결 예외 |
| 2 | chunks 테이블 레코드 수 | 0건 또는 테이블 없음 |
| 3 | embeddings_e5 테이블 레코드 수 | 0건 또는 테이블 없음 |
| 4 | 벡터 차원 | 384 아닌 경우 |

### 출력 형식

성공:
```
[✅] Postgres 연결 (localhost:5432/skn_project)
[✅] chunks 테이블: 1,243건
[✅] embeddings_e5 테이블: 1,198건
[✅] 벡터 차원: 384

모든 헬스 체크 통과 ✅
```

실패:
```
[❌] Postgres 연결 실패: could not connect to server (port 5432)
헬스 체크 실패 — 위 항목을 확인하세요.
```

- 실패 시 `sys.exit(1)` (CI/자동화 연동 가능)
- 단계 중 실패 발생 시 이후 단계는 SKIP 표시 후 종료

---

## README 추가 내용

`## 서비스 구성` 섹션 추가:

```markdown
## 서비스 구성

| 서비스   | 포트  | 볼륨          | 설명                        |
|---------|-------|---------------|-----------------------------|
| postgres | 5432  | postgres_data | PostgreSQL + pgvector DB    |
| (앱)     | 8501  | —             | Streamlit (로컬 직접 실행)  |

## 빠른 시작

1. `cp .env.example .env` — 환경변수 설정
2. `docker-compose up -d` — DB 시작
3. `python scripts/healthcheck.py` — DB 상태 확인
4. `streamlit run app.py` — 앱 실행 (http://localhost:8501)
```

---

## day-14.md 원데이 검증 노트

기존 체크리스트를 완성된 단계별 검증 노트로 교체:

- 전제 조건 (Docker, Python, 모델 파일 위치)
- 단계별 명령어 + 기대 출력
- 자주 묻는 문제 (포트 충돌, 모델 파일 없음 등)

---

## 성공 기준

1. `python scripts/healthcheck.py` 실행 시 4단계 출력 후 exit 0
2. DB 없는 환경에서 exit 1 + 오류 메시지
3. README에 서비스 표 + 빠른 시작 4단계 존재
4. `docs/dev-log/milestones/day-14.md` 원데이 검증 노트 완성
