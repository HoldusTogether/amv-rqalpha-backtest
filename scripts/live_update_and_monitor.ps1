<#
.SYNOPSIS
  一键更新数据 + 实盘监控
.DESCRIPTION
  1. 启动指南针和通达信，等待最新日线数据下载
  2. 提取 AMV、概念、ETF 数据
  3. 运行 AMV 实盘监控脚本，信号变化时推送到微信
#>

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$LiveMonitor = Join-Path $Root "live\live_monitor.py"

# ── 路径 ──
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

# ── Step 0: 检查可执行文件 ──
Write-Step "环境检查"
if (-not (Test-Path $Python)) { Write-Host "ERROR: Python 未找到 ${Python}"; exit 1 }
if (-not (Test-Path $ZnzExe)) { Write-Info "指南针未安装，跳过 AMV 更新" }
if (-not (Test-Path $TdxExe)) { Write-Info "通达信未安装，跳过 ETF 更新" }

# ── Step 1: 启动指南针 + 通达信 ──
Write-Step "启动数据源软件"

$ZnzBefore = if (Test-Path $ZnzData) { (Get-Item $ZnzData).LastWriteTime } else { Get-Date "2000-01-01" }
$TdxBefore = if (Test-Path $TdxData) { (Get-Item $TdxData).LastWriteTime } else { Get-Date "2000-01-01" }

$processes = @()
if (Test-Path $ZnzExe) {
  $p = Start-Process -FilePath $ZnzExe -PassThru
  Write-Info "指南针已启动 (PID: $($p.Id))"
  $processes += $p
}
if (Test-Path $TdxExe) {
  $p = Start-Process -FilePath $TdxExe -PassThru
  Write-Info "通达信已启动 (PID: $($p.Id))"
  $processes += $p
}

if ($processes.Count -eq 0) {
  Write-Host "没有可用的数据源，直接运行监控"
  & $Python $LiveMonitor
  exit 0
}

# 等待数据更新 (最多 120s)
Write-Info "等待数据下载中..."
$waited = 0
$znzDone = -not (Test-Path $ZnzExe)
$tdxDone = -not (Test-Path $TdxExe)

while ($waited -lt 120) {
  Start-Sleep -Seconds 10
  $waited += 10

  if (-not $znzDone -and (Test-Path $ZnzData)) {
    $mtime = (Get-Item $ZnzData).LastWriteTime
    if ($mtime -gt $ZnzBefore) {
      Write-Info "指南针数据已更新 ($mtime)"
      $znzDone = $true
    }
  }
  if (-not $tdxDone -and (Test-Path $TdxData)) {
    $mtime = (Get-Item $TdxData).LastWriteTime
    if ($mtime -gt $TdxBefore) {
      Write-Info "通达信数据已更新 ($mtime)"
      $tdxDone = $true
    }
  }
  if ($znzDone -and $tdxDone) { break }
}

Write-Info "等待结束 (耗时 ${waited}s)"

# 关闭软件
Write-Info "关闭数据源软件..."
foreach ($p in $processes) {
  Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 3

# ── Step 2: 数据提取 ──
Write-Step "提取 AMV 数据"
if (Test-Path $ZnzExe) {
  & $Python (Join-Path $Root "scripts\extract_amv_klines.py")
} else {
  Write-Info "跳过 (指南针未安装)"
}

Write-Step "更新概念数据 (AKShare)"
& $Python (Join-Path $Root "scripts\fetch_concept_data_akshare.py")

Write-Step "更新 ETF 数据 (通达信)"
if (Test-Path $TdxExe) {
  & $Python (Join-Path $Root "scripts\build_etf_flow_from_tdx.py")
} else {
  Write-Info "跳过 (通达信未安装)"
}

# ── Step 3: 运行监控 ──
Write-Step "运行实盘监控"
& $Python $LiveMonitor
if ($LASTEXITCODE -ne 0) {
  Write-Host "监控运行失败 (exit code: $LASTEXITCODE)" -ForegroundColor Red
  exit $LASTEXITCODE
}

Write-Host "`n全部完成！" -ForegroundColor Green
