<#
.SYNOPSIS
  One-click data update + live monitor with auto-login
.DESCRIPTION
  1. Launch Compass/TDX, auto-login via SendKeys, wait for data download
  2. Extract AMV, concept, ETF data
  3. Run AMV live monitor with WeChat push
#>

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$LiveMonitor = Join-Path $Root "live\live_monitor.py"

# -- paths --
$ZnzExe   = "D:\Program Files (x86)\zhinanzhen\IMMainV2.exe"
$ZnzData  = "D:\Program Files (x86)\zhinanzhen\ANALYSE\Data\ChinaStk\Z_SK\day.vdat"
$TdxExe   = "D:\new_tdx\tdxw.exe"
$TdxData  = "D:\new_tdx\vipdoc\sh\lday\sh000001.day"

function Write-Step {
  param([string]$Msg)
  Write-Host "`n=== $Msg ===" -ForegroundColor Cyan
}

function Write-Info {
  param([string]$Msg)
  Write-Host "  $Msg"
}

function Send-LoginKeys {
  param([string[]]$WindowTitles, [int]$MaxWaitSec = 20)

  $wshell = New-Object -ComObject wscript.shell
  for ($i = 0; $i -lt $MaxWaitSec; $i++) {
    foreach ($title in $WindowTitles) {
      $found = $wshell.AppActivate($title)
      if ($found) {
        Start-Sleep -Milliseconds 300
        $wshell.SendKeys("~")
        Write-Info ("  Login sent to window: " + $title)
        return $true
      }
    }
    Start-Sleep -Seconds 1
  }
  Write-Info ("  Window not found: " + ($WindowTitles -join ", "))
  return $false
}

# -- Step 0: env check --
Write-Step "Check environment"
if (-not (Test-Path $Python)) { Write-Host "ERROR: Python not found: $Python"; exit 1 }
if (-not (Test-Path $ZnzExe)) { Write-Info "Compass not found, skip AMV update" }
if (-not (Test-Path $TdxExe)) { Write-Info "TDX not found, skip ETF update" }

# -- Step 1: launch data sources --
Write-Step "Launch data software"

$ZnzBefore = if (Test-Path $ZnzData) { (Get-Item $ZnzData).LastWriteTime } else { Get-Date "2000-01-01" }
$TdxBefore = if (Test-Path $TdxData) { (Get-Item $TdxData).LastWriteTime } else { Get-Date "2000-01-01" }

$processes = @()
if (Test-Path $ZnzExe) {
  $p = Start-Process -FilePath $ZnzExe -PassThru
  Write-Info ("Compass started (PID: " + $p.Id + ")")
  $processes += $p
}
if (Test-Path $TdxExe) {
  $p = Start-Process -FilePath $TdxExe -PassThru
  Write-Info ("TDX started (PID: " + $p.Id + ")")
  $processes += $p
}

if ($processes.Count -eq 0) {
  Write-Host "No data source, run monitor directly"
  & $Python $LiveMonitor
  exit 0
}

# -- SendKeys auto-login --
Write-Info "Sending login keystrokes..."
if (Test-Path $ZnzExe) {
  Send-LoginKeys -WindowTitles @("指南针", "IMMainV2") -MaxWaitSec 20
}
if (Test-Path $TdxExe) {
  Send-LoginKeys -WindowTitles @("登录通达信", "通达信金融终端", "通达信") -MaxWaitSec 20
}

# wait for data update (max 120s since launch)
Write-Info "Waiting for data download..."
$waited = 0
$znzDone = -not (Test-Path $ZnzExe)
$tdxDone = -not (Test-Path $TdxExe)

while ($waited -lt 120) {
  Start-Sleep -Seconds 10
  $waited += 10

  if (-not $znzDone -and (Test-Path $ZnzData)) {
    $mtime = (Get-Item $ZnzData).LastWriteTime
    if ($mtime -gt $ZnzBefore) {
      Write-Info ("Compass data updated (" + $mtime + ")")
      $znzDone = $true
    }
  }
  if (-not $tdxDone -and (Test-Path $TdxData)) {
    $mtime = (Get-Item $TdxData).LastWriteTime
    if ($mtime -gt $TdxBefore) {
      Write-Info ("TDX data updated (" + $mtime + ")")
      $tdxDone = $true
    }
  }
  if ($znzDone -and $tdxDone) { break }
}

Write-Info ("Wait done (" + $waited + "s)")

# close software
Write-Info "Closing data software..."
foreach ($p in $processes) {
  Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 3

# -- Step 2: extract data --
Write-Step "Extract AMV data"
if (Test-Path $ZnzExe) {
  & $Python (Join-Path $Root "scripts\extract_amv_klines.py")
} else {
  Write-Info "Skip (Compass not installed)"
}

Write-Step "Update concept data (AKShare)"
& $Python (Join-Path $Root "scripts\fetch_concept_data_akshare.py")

Write-Step "Update ETF data (TDX)"
if (Test-Path $TdxExe) {
  & $Python (Join-Path $Root "scripts\build_etf_flow_from_tdx.py")
} else {
  Write-Info "Skip (TDX not installed)"
}

# -- Step 3: run monitor --
Write-Step "Run live monitor"
& $Python $LiveMonitor
if ($LASTEXITCODE -ne 0) {
  Write-Host ("Monitor failed (exit code: " + $LASTEXITCODE + ")") -ForegroundColor Red
  exit $LASTEXITCODE
}

Write-Host "DONE" -ForegroundColor Green
