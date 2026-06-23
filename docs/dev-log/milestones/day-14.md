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
