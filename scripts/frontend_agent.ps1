<# .SYNOPSIS
  前端专家 Agent - amv-rqalpha-backtest 仪表盘前端管理系统
.DESCRIPTION
  审查、优化、维护 web/ 目录下的前端界面（HTML/CSS/JS）。
  支持 --review 审查模式、--improve 改进模式、--screenshot 截图模式。
  可在 Windows 任务计划程序中设为每周定时运行。

  用法:
    .\scripts\frontend_agent.ps1 --review       仅审查并生成报告
    .\scripts\frontend_agent.ps1 --improve      审查 + 执行 1-3 项改进
    .\scripts\frontend_agent.ps1 --screenshot   仅截图验证
    .\scripts\frontend_agent.ps1 --all          完整运行（默认）
#>

param(
  [switch]$Review,
  [switch]$Improve,
  [switch]$Screenshot,
  [switch]$All
)

$Root = Split-Path -Parent $PSScriptRoot
$WebDir = Join-Path $Root "web"
$ReviewDir = Join-Path $WebDir "_reviews"
$Date = Get-Date -Format "yyyy-MM-dd"
$ReviewFile = Join-Path $ReviewDir "review-$Date.md"

# 创建审查目录
if (-not (Test-Path $ReviewDir)) { New-Item -ItemType Directory -Path $ReviewDir -Force | Out-Null }

$Mode = if ($Review) { "review" } elseif ($Improve) { "improve" } elseif ($Screenshot) { "screenshot" } else { "all" }

Write-Host "=== 前端专家 Agent ===" -ForegroundColor Cyan
Write-Host "项目: amv-rqalpha-backtest" -ForegroundColor Cyan
Write-Host "日期: $Date" -ForegroundColor Cyan
Write-Host "模式: $Mode" -ForegroundColor Cyan
Write-Host ""

# ----- 1. 检查文件完整性 -----
function Check-Files {
  $files = @(
    (Join-Path $WebDir "index.html"),
    (Join-Path $WebDir "styles.css"),
    (Join-Path $WebDir "app.js"),
    (Join-Path $WebDir "data/dashboard.json")
  )
  $missing = @()
  foreach ($f in $files) {
    if (-not (Test-Path $f)) { $missing += $f }
  }
  if ($missing.Count -gt 0) {
    Write-Host "[WARN] 缺失文件:" -ForegroundColor Yellow
    $missing | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
  } else {
    Write-Host "[OK] 所有前端文件存在" -ForegroundColor Green
  }
  return $missing.Count -eq 0
}

# ----- 2. 检查服务器 -----
function Check-Server {
  $proc = Get-Process -Name "node" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -match "app\.js"
  }
  if ($proc) {
    Write-Host "[OK] Node 服务器运行中 (PID: $($proc.Id))" -ForegroundColor Green
    return $true
  }
  Write-Host "[..] Node 服务器未运行" -ForegroundColor Yellow
  return $false
}

# ----- 3. 生成审查摘要 -----
function Generate-Review {
  param([bool]$FilesOk, [bool]$ServerRunning)

  $lines = @()
  $lines += "# 前端审查报告"
  $lines += ""
  $lines += "日期: $Date"
  $lines += "模式: $Mode"
  $lines += ""

  # 文件行数统计
  $htmlLines = (Get-Content (Join-Path $WebDir "index.html") | Measure-Object).Count
  $cssLines = (Get-Content (Join-Path $WebDir "styles.css") | Measure-Object).Count
  $jsLines = (Get-Content (Join-Path $WebDir "app.js") | Measure-Object).Count
  $jsonSize = (Get-Item (Join-Path $WebDir "data/dashboard.json")).Length / 1KB

  $lines += "## 文件概览"
  $lines += "- index.html ($htmlLines 行)"
  $lines += "- styles.css ($cssLines 行)"
  $lines += "- app.js ($jsLines 行)"
  $lines += "- dashboard.json ($('{0:N1}' -f $jsonSize) KB)"
  $lines += ""

  # dashboard.json 数据概览
  try {
    $json = Get-Content (Join-Path $WebDir "data/dashboard.json") -Encoding UTF8 | ConvertFrom-Json
    $signalCount = $json.signals.Count
    $tradeCount = $json.trades.Count
    $portfolioCount = $json.portfolio.Count
    $summary = $json.summary
    $lines += "## 数据概览"
    $lines += "- 回测区间: $($summary.start_date) ~ $($summary.end_date)"
    $lines += "- 总收益: $('{0:P2}' -f $summary.total_return)"
    $lines += "- 最大回撤: $('{0:P2}' -f $summary.max_drawdown)"
    $lines += "- 期末资产: $('{0:N0}' -f $summary.ending_value)"
    $lines += "- 交易次数: $($summary.trades)"
    $lines += "- 信号数量: $signalCount"
    $lines += "- 交易记录: $tradeCount"
    $lines += "- 净值数据: $portfolioCount 个交易日"
    $lines += ""
  } catch {
    $lines += "## 数据概览"
    $lines += "- dashboard.json 解析失败: $_"
    $lines += ""
  }

  $lines += "## 系统状态"
  $lines += "- 文件完整性: $(if ($FilesOk) { 'OK' } else { '缺失文件' })"
  $lines += "- 服务器: $(if ($ServerRunning) { '运行中' } else { '未运行' })"
  $lines += ""

  return $lines -join "`n"
}

# ----- 4. 保存报告 -----
function Save-Review {
  param([string]$Content)
  $Content | Out-File -FilePath $ReviewFile -Encoding UTF8
  Write-Host "[OK] 审查报告已保存: $ReviewFile" -ForegroundColor Green
}

# ----- 主流程 -----
$allOk = Check-Files
$serverRunning = Check-Server

# 写入审查报告
if ($Mode -eq "review" -or $Mode -eq "all" -or $Mode -eq "improve") {
  $report = Generate-Review -FilesOk $allOk -ServerRunning $serverRunning
  Save-Review -Content $report
}

# 截图验证
if ($Mode -eq "screenshot" -or $Mode -eq "all") {
  if (-not $serverRunning) {
    Write-Host "[..] 尝试启动服务器..." -ForegroundColor Yellow
    $serverDir = $WebDir
    Start-Process -FilePath "node" -ArgumentList "app.js" -WorkingDirectory $serverDir -WindowStyle Hidden
    Start-Sleep -Seconds 3
    $serverRunning = Check-Server
  }

  if ($serverRunning) {
    Write-Host "[..] 正在截图... (需要 Playwright)" -ForegroundColor Yellow
    $screenshotScript = @"
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  
  // 桌面端 1440px
  const desktop = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await desktop.goto('http://localhost:8081', { waitUntil: 'networkidle', timeout: 15000 });
  await desktop.waitForTimeout(2000);
  await desktop.screenshot({ path: '$ReviewDir'.replace(/\\/g, '/') + '/screenshot-desktop-$Date.png', fullPage: true });
  await desktop.close();

  // 移动端 375px
  const mobile = await browser.newPage({ viewport: { width: 375, height: 812 } });
  await mobile.goto('http://localhost:8081', { waitUntil: 'networkidle', timeout: 15000 });
  await mobile.waitForTimeout(2000);
  await mobile.screenshot({ path: '$ReviewDir'.replace(/\\/g, '/') + '/screenshot-mobile-$Date.png', fullPage: true });
  await mobile.close();

  await browser.close();
  console.log('截图完成');
})();
"@
    $screenshotFile = Join-Path $env:TEMP "screenshot-$Date.js"
    $screenshotScript | Out-File -FilePath $screenshotFile -Encoding UTF8

    try {
      $result = & node $screenshotFile 2>&1
      if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] 截图保存到 $ReviewDir" -ForegroundColor Green
      } else {
        Write-Host "[WARN] 截图失败: $result" -ForegroundColor Yellow
        Write-Host "[WARN] 确保已安装 playwright: npm install playwright" -ForegroundColor Yellow
      }
    } catch {
      Write-Host "[WARN] 截图执行异常: $_" -ForegroundColor Yellow
    }
    Remove-Item $screenshotFile -Force -ErrorAction SilentlyContinue
  } else {
    Write-Host "[WARN] 跳过截图：服务器未运行" -ForegroundColor Yellow
  }
}

Write-Host ""
Write-Host "=== 前端专家 Agent 完成 ===" -ForegroundColor Cyan
Write-Host "报告: $ReviewFile" -ForegroundColor Cyan

# 改进模式下输出操作提示
if ($Mode -eq "improve" -or $Mode -eq "all") {
  Write-Host ""
  Write-Host "=== 优化建议 ===" -ForegroundColor Magenta
  Write-Host "在 Codex 中打开此项目，使用 skills 前端专家技能进行优化:"
  Write-Host "  @frontend-expert 审查前端并优化"
  Write-Host "或手动指出具体优化方向："
  Write-Host "  - 图表交互增强"
  Write-Host "  - 深色模式"
  Write-Host "  - 表格导出功能"
  Write-Host "  - 加载动画优化"
  Write-Host "  - 移动端体验"
  Write-Host ""
}
