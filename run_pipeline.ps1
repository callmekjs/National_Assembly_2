param(
  [string]$PgPort = "5433",
  [switch]$SkipCrawl
)

$ErrorActionPreference = "Stop"

$env:PG_PORT = $PgPort

if (-not $SkipCrawl) {
  .\.venv\Scripts\python.exe crawling.py
}

.\.venv\Scripts\python.exe -m service.etl.extractor.extractor
.\.venv\Scripts\python.exe -m service.etl.transform.pipeline
.\.venv\Scripts\python.exe -m service.etl.loader.loader_cli db create
.\.venv\Scripts\python.exe -m service.etl.loader.loader_cli load doc --jsonl-dir data/transform/final
.\.venv\Scripts\python.exe -m service.etl.loader.loader_cli load vector
.\.venv\Scripts\python.exe -m service.rag.evaluate_retrieval --pg-port $PgPort --top-k 3

Write-Host "`n[run_pipeline.ps1] completed" -ForegroundColor Green
