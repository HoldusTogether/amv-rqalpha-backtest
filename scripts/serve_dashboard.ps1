$Root = Split-Path -Parent $PSScriptRoot
$Web = Join-Path $Root "web"
$PidFile = Join-Path $Web "server.pid"
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (Test-Path -LiteralPath $PidFile) {
  $ExistingPid = Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue
  if ($ExistingPid) {
    $Existing = Get-Process -Id $ExistingPid -ErrorAction SilentlyContinue
    if ($Existing) {
      Write-Output "Dashboard already running at http://127.0.0.1:8765"
      exit 0
    }
  }
}

$Process = Start-Process `
  -FilePath $Python `
  -ArgumentList @("-m", "http.server", "8765", "--bind", "127.0.0.1", "--directory", $Web) `
  -WindowStyle Hidden `
  -PassThru

Set-Content -LiteralPath $PidFile -Value $Process.Id
Write-Output "Dashboard running at http://127.0.0.1:8765"

