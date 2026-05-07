param(
  [string]$Query = "대북정책 핵심 쟁점은?",
  [string]$Committee = "",
  [string]$DateFrom = "",
  [string]$DateTo = "",
  [int]$TopK = 5,
  [string]$PgPort = "5433"
)

$ErrorActionPreference = "Stop"

$env:PG_PORT = $PgPort

$argsList = @(
  "-m", "service.rag.qa_demo",
  "--query", $Query,
  "--top-k", "$TopK",
  "--pg-port", $PgPort
)

if ($Committee) { $argsList += @("--committee", $Committee) }
if ($DateFrom) { $argsList += @("--date-from", $DateFrom) }
if ($DateTo) { $argsList += @("--date-to", $DateTo) }

& .\.venv\Scripts\python.exe @argsList
