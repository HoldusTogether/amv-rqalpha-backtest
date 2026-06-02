<#
.SYNOPSIS
  自动启动指南针和通达信，等待数据更新后关闭，然后执行完整数据更新流程。
.DESCRIPTION
  1. 启动指南针 (IMMainV2.exe)，等待下载最新日线数据
  2. 启动通达信 (tdxw.exe)，等待下载最新 .day 文件
  3. 关闭两个软件（释放文件锁）
  4. 执行 update_data.ps1（AMV + 概念 + ETF + bundle）
#>

$Root = Split-Path -Parent $PSScriptRoot
$LogFile = Join-Path $Root "web\.task-output\launch_apps.log"
$LogDir = Split-Path $LogFile -Parent
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

function Write-Log {
  param([string]$Msg)
  $line = "$(Get-Date -Format 'HH:mm:ss') $Msg"
  Write-Host $line
  Add-Content -Path $LogFile -Value $line
}

# ── 路径 ──
$ZnzExe   = "D:\Program Files (x86)\zhinanzhen\IMMainV2.exe"
$ZnzData  = "D:\Program Files (x86)\zhinanzhen\ANALYSE\Data\ChinaStk\Z_SK\day.vdat"
$TdxExe   = "D:\new_tdx\tdxw.exe"
$TdxData  = "D:\new_tdx\vipdoc\sh\lday\sh000001.day"

# ── 检查可执行文件是否存在 ──
if (-not (Test-Path $ZnzExe))  { Write-Log "ERROR: 指南针未找到 $ZnzExe"; exit 1 }
if (-not (Test-Path $TdxExe))  { Write-Log "ERROR: 通达信未找到 $TdxExe";  exit 1 }

# ── 记录启动前的文件修改时间 ──
$ZnzBefore = if (Test-Path $ZnzData) { (Get-Item $ZnzData).LastWriteTime } else { Get-Date "2000-01-01" }
$TdxBefore = if (Test-Path $TdxData) { (Get-Item $TdxData).LastWriteTime } else { Get-Date "2000-01-01" }

Write-Log "=== 启动指南针 ==="
$znz = Start-Process -FilePath $ZnzExe -PassThru
Write-Log "  指南针 PID: $($znz.Id)"

Write-Log "=== 启动通达信 ==="
$tdx = Start-Process -FilePath $TdxExe -PassThru
Write-Log "  通达信 PID: $($tdx.Id)"

# ── 等待数据更新（最多 120 秒）──
Write-Log "  等待数据下载中..."
$waited = 0
$znzDone = $false
$tdxDone = $false
while ($waited -lt 120) {
  Start-Sleep -Seconds 10
  $waited += 10

  if (-not $znzDone -and (Test-Path $ZnzData)) {
    $mtime = (Get-Item $ZnzData).LastWriteTime
    if ($mtime -gt $ZnzBefore) {
      Write-Log "  指南针数据已更新 ($mtime)"
      $znzDone = $true
    }
  }
  if (-not $tdxDone -and (Test-Path $TdxData)) {
    $mtime = (Get-Item $TdxData).LastWriteTime
    if ($mtime -gt $TdxBefore) {
      Write-Log "  通达信数据已更新 ($mtime)"
      $tdxDone = $true
    }
  }
  if ($znzDone -and $tdxDone) { break }
}

Write-Log "  等待结束（耗时 ${waited}s）"

# ── 关闭软件 ──
Write-Log "=== 关闭指南针 ==="
Stop-Process -Id $znz.Id -Force -ErrorAction SilentlyContinue

Write-Log "=== 关闭通达信 ==="
Stop-Process -Id $tdx.Id -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3  # 等待文件锁释放

# ── 执行数据更新 ──
Write-Log "=== 开始数据更新 ==="
& "$PSScriptRoot\update_data.ps1"
Write-Log "=== 全部完成 ==="
