<#
.SYNOPSIS
  注册 AMV 实盘监控每日定时任务（交易日盘后）
.DESCRIPTION
  创建 Windows 计划任务，每个交易日 15:30 自动运行 live_update_and_monitor.ps1
  需要用户登录状态（因为要打开指南针/通达信）
#>

$TaskName = "AMV Live Monitor"
$Root = Split-Path -Parent $PSScriptRoot
$ScriptPath = Join-Path $Root "scripts\live_update_and_monitor.ps1"

# ── 检查脚本是否存在 ──
if (-not (Test-Path $ScriptPath)) {
    Write-Host "ERROR: 脚本不存在 $ScriptPath" -ForegroundColor Red
    exit 1
}

# ── 删除旧任务（如有） ──
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "删除已有任务: $TaskName"
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# ── 创建触发器：每工作日 15:30 ──
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "15:30"

# ── 创建任务 ──
$action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -RunLevel Highest -LogonType Interactive

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force

if ($?) {
    Write-Host "`n✅ 任务已注册: $TaskName" -ForegroundColor Green
    Write-Host "  触发器: 交易日 15:30"
    Write-Host "  脚本: $ScriptPath"
    Write-Host "  用户: $env:USERDOMAIN\$env:USERNAME"
    Write-Host "`n如需修改时间，运行:"
    Write-Host "  Set-ScheduledTask -TaskName '$TaskName' -Trigger (New-ScheduledTaskTrigger -Daily -At '16:00')"
    Write-Host "`n如需手动测试，运行:"
    Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
} else {
    Write-Host "ERROR: 注册失败" -ForegroundColor Red
}
