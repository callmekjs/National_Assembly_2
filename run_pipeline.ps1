param(
  [string]$PgPort = "5433",
  [switch]$SkipCrawl,
  [switch]$VerifyIdempotent
)

$ErrorActionPreference = "Stop"

$env:PG_PORT = $PgPort
if (-not $env:PYTHONIOENCODING) {
  $env:PYTHONIOENCODING = "utf-8"
}

function Write-PipelineHint {
  param([string]$StepName)
  Write-Host "[pipeline] hints:" -ForegroundColor Yellow
  switch ($StepName) {
    { $_ -in @("crawl", "extract", "transform") } {
      Write-Host "  - 디스크/네트워크 오류인지 확인합니다. venv가 활성화되어 있는지 확인합니다."
    }
    "db_create" {
      Write-Host "  - Docker 컨테이너 이름이 SKN18-3rd인지, psql이 컨테이너 안에 있는지 확인합니다."
      Write-Host "  - 수동 스키마 적용이 필요할 수 있습니다 (OPERATIONS.md 참고)."
    }
    "load_doc" {
      Write-Host "  - data/transform/final 에 *.jsonl 이 있는지 확인합니다."
      Write-Host "  - PG_HOST/PG_PORT/PG_DB가 실제 Postgres와 일치하는지 확인합니다 ($env:PG_PORT)."
    }
    "load_vector" {
      Write-Host '  - `embeddings_e5` 테이블이 없으면 다른 DB 포트에 붙었을 가능성이 큽니다. PG_PORT=5433 확인.'
      Write-Host "  - transform/load doc 이후에 실행했는지 확인합니다."
    }
    "evaluate" {
      Write-Host "  - evaluate_retrieval 은 검색 단계입니다. DB 연결 및 벡터 적재 상태를 확인합니다."
      Write-Host "  - 고정 평가셋: service/rag/eval_queries_fixed.json (기본)"
    }
    default {
      Write-Host "  - OPERATIONS.md 의 자주 나는 오류 섹션을 참고합니다."
      Write-Host "  - PG_PORT=$env:PG_PORT 가 프로젝트 DB와 일치하는지 확인합니다."
    }
  }
}

function Invoke-PipelineStep {
  param(
    [Parameter(Mandatory = $true)][string]$StepName,
    [Parameter(Mandatory = $true)][string[]]$PythonArgs
  )
  Write-Host ""
  Write-Host "[pipeline][$StepName] START" -ForegroundColor Cyan
  & .\.venv\Scripts\python.exe @PythonArgs
  if ($LASTEXITCODE -ne 0) {
    Write-Host "[pipeline][$StepName] FAIL (exit=$LASTEXITCODE)" -ForegroundColor Red
    Write-PipelineHint -StepName $StepName
    exit $LASTEXITCODE
  }
  Write-Host "[pipeline][$StepName] OK" -ForegroundColor Green
}

Write-Host "[pipeline] PG_PORT=$env:PG_PORT PYTHONIOENCODING=$env:PYTHONIOENCODING" -ForegroundColor DarkGray

if (-not $SkipCrawl) {
  Invoke-PipelineStep -StepName "crawl" -PythonArgs @("crawling.py")
}

Invoke-PipelineStep -StepName "extract" -PythonArgs @("-m", "service.etl.extractor.extractor")
Invoke-PipelineStep -StepName "transform" -PythonArgs @("-m", "service.etl.transform.pipeline")
Invoke-PipelineStep -StepName "db_create" -PythonArgs @("-m", "service.etl.loader.loader_cli", "db", "create")

function Invoke-LoadSteps {
  Invoke-PipelineStep -StepName "load_doc" -PythonArgs @(
    "-m", "service.etl.loader.loader_cli", "load", "doc",
    "--jsonl-dir", "data/transform/final"
  )
  Invoke-PipelineStep -StepName "load_vector" -PythonArgs @(
    "-m", "service.etl.loader.loader_cli", "load", "vector"
  )
}

Invoke-LoadSteps

if ($VerifyIdempotent) {
  Write-Host ""
  Write-Host "[pipeline] VerifyIdempotent: running load doc + load vector a second time" -ForegroundColor Magenta
  Invoke-LoadSteps
}

Invoke-PipelineStep -StepName "evaluate" -PythonArgs @(
  "-m", "service.rag.evaluate_retrieval",
  "--pg-port", $PgPort
)

Write-Host ""
Write-Host "[run_pipeline.ps1] completed" -ForegroundColor Green
