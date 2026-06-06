<#
.SYNOPSIS
  One-click data update + live monitor
.DESCRIPTION
  Launch Compass/TDX with correct WorkingDirectory (saved credentials work),
  auto-login via Enter key, trigger TDX .933 download, wait for completion,
  extract data, run AMV live monitor.
#>

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$LiveMonitor = Join-Path $Root "live\live_monitor.py"
$WechatHelper = Join-Path $Root "live\wechat_push.py"

# -- paths --
$ZnzDir   = "D:\Program Files (x86)\zhinanzhen"
$ZnzExe   = "$ZnzDir\WavMain.exe"
$ZnzData  = "$ZnzDir\ANALYSE\Data\ChinaStk\Z_SK\day.vdat"
$TdxDir   = "D:\new_tdx"
$TdxExe   = "$TdxDir\tdxw.exe"
$TdxData  = "$TdxDir\vipdoc\sh\lday\sh000001.day"

# -- Win32 P/Invoke (single Add-Type block) --
Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public class Win32C {
  [DllImport("user32.dll")]
  public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll", SetLastError=true)]
  public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
  [DllImport("user32.dll", SetLastError=true)]
  public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
  [DllImport("user32.dll", CharSet=CharSet.Auto)]
  public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
  [DllImport("user32.dll", CharSet=CharSet.Auto)]
  public static extern int GetClassName(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
  [DllImport("user32.dll")]
  public static extern bool IsWindowVisible(IntPtr hWnd);

  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

  public static IntPtr FindMainWindow(uint targetPid) {
    IntPtr result = IntPtr.Zero;
    int maxArea = 0;
    EnumWindows(delegate(IntPtr hWnd, IntPtr lParam) {
      uint wPid;
      GetWindowThreadProcessId(hWnd, out wPid);
      if (wPid == targetPid) {
        StringBuilder sb = new StringBuilder(256);
        GetWindowText(hWnd, sb, 256);
        int len = sb.Length;
        if (len > 0) {
          RECT rect;
          GetWindowRect(hWnd, out rect);
          int area = (rect.Right - rect.Left) * (rect.Bottom - rect.Top);
          if (area > maxArea) { maxArea = area; result = hWnd; }
        }
      }
      return true;
    }, IntPtr.Zero);
    return result;
  }

  public static IntPtr FindDialogForPid(uint targetPid) {
    IntPtr result = IntPtr.Zero;
    EnumWindows(delegate(IntPtr hWnd, IntPtr lParam) {
      uint wPid;
      GetWindowThreadProcessId(hWnd, out wPid);
      if (wPid == targetPid) {
        StringBuilder sb2 = new StringBuilder(256);
        GetClassName(hWnd, sb2, 256);
        if (sb2.ToString() == "#32770") {
          RECT r;
          GetWindowRect(hWnd, out r);
          if ((r.Right - r.Left) > 100 && (r.Bottom - r.Top) > 100) {
            result = hWnd;
            return false;
          }
        }
      }
      return true;
    }, IntPtr.Zero);
    return result;
  }

  [StructLayout(LayoutKind.Sequential)]
  public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
  [DllImport("user32.dll")]
  public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

  public static List<string> FindVisibleTitlesContaining(string pattern, string exclude) {
    var results = new List<string>();
    EnumWindows(delegate(IntPtr hWnd, IntPtr lParam) {
      if (!IsWindowVisible(hWnd)) return true;
      StringBuilder sb = new StringBuilder(256);
      GetWindowText(hWnd, sb, 256);
      var title = sb.ToString();
      if (title.IndexOf(pattern, StringComparison.Ordinal) >= 0
          && (string.IsNullOrEmpty(exclude) || title.IndexOf(exclude, StringComparison.Ordinal) < 0)) {
        results.Add(title);
      }
      return true;
    }, IntPtr.Zero);
    return results;
  }
}
"@

function Write-Step {
  param([string]$Msg)
  Write-Output ""
  Write-Output "=== $Msg ==="
}

function Write-Info {
  param([string]$Msg)
  Write-Output "  $Msg"
}

# -- Screenshot capture (primary monitor) for diagnostics --
function Save-Screenshot {
  param([string]$Tag)
  $shotPath = Join-Path $Root ("scripts\diag_{0}_{1}.png" -f $Tag, (Get-Date -Format "HHmmss"))
  try {
    Add-Type -AssemblyName System.Drawing -ErrorAction SilentlyContinue
    Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen
    $bmp = New-Object System.Drawing.Bitmap $screen.Bounds.Width, $screen.Bounds.Height
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($screen.Bounds.Location, [System.Drawing.Point]::Empty, $screen.Bounds.Size)
    $bmp.Save($shotPath, [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose()
    Write-Info ("  Screenshot: " + $shotPath)
  } catch {
    Write-Info ("  Screenshot failed: " + $_.Exception.Message)
  }
}

# -- SendKeys helper: focus TDX window, then send a key --
function Send-TdxKey {
  param([IntPtr]$Hwnd, [string]$Key, [int]$DelayMs = 300)
  if ($Hwnd -ne [IntPtr]::Zero) {
    [Win32C]::SetForegroundWindow($Hwnd) | Out-Null
    Start-Sleep -Milliseconds 200
  }
  [System.Windows.Forms.SendKeys]::SendWait($Key)
  Start-Sleep -Milliseconds $DelayMs
}

# -- WeChat push (calls Python helper) --
function Send-WeChatNotice {
  param([string]$Title, [string]$Content)
  if (-not (Test-Path $WechatHelper)) {
    Write-Info "  WeChat: helper not found ($WechatHelper)"
    return $false
  }
  $output = & $Python $WechatHelper $Title $Content 2>&1
  $code = $LASTEXITCODE
  if ($code -eq 0) {
    Write-Info "  WeChat: sent - $Title"
    return $true
  } else {
    Write-Info "  WeChat: failed (exit=$code) - $output"
    return $false
  }
}

# -- UIA helper: try to find and click a button --
function Invoke-UIAButton {
  param([string[]]$WindowPatterns, [string]$ButtonName, [int]$MaxWaitSec = 15)

  Add-Type -AssemblyName UIAutomationClient -ErrorAction SilentlyContinue
  Add-Type -AssemblyName UIAutomationTypes -ErrorAction SilentlyContinue
  $root = [System.Windows.Automation.AutomationElement]::RootElement
  $condTrue = [System.Windows.Automation.Condition]::TrueCondition

  for ($i = 0; $i -lt $MaxWaitSec; $i++) {
    Start-Sleep -Seconds 1
    $allWindows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $condTrue)
    foreach ($w in $allWindows) {
      $title = $w.Current.Name
      foreach ($pat in $WindowPatterns) {
        if ($title -like "*$pat*") {
          $nameCond = New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::NameProperty, $ButtonName
          )
          $btn = $w.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $nameCond)
          if ($btn) {
            try {
              $invoke = $btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
              $invoke.Invoke()
              Write-Info ("  UIA clicked '" + $ButtonName + "' on '" + $title + "'")
              return $true
            } catch {}
          }
        }
      }
    }
  }
  return $false
}

# -- SendKeys helper: AppActivate then Send Enter --
function Send-EnterToWindow {
  param([string[]]$WindowPatterns, [int]$MaxWaitSec = 15)

  Add-Type -AssemblyName Microsoft.VisualBasic
  Add-Type -AssemblyName System.Windows.Forms
  for ($i = 0; $i -lt $MaxWaitSec; $i++) {
    Start-Sleep -Seconds 1
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $condTrue = [System.Windows.Automation.Condition]::TrueCondition
    $allWindows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $condTrue)
    foreach ($w in $allWindows) {
      $title = $w.Current.Name
      foreach ($pat in $WindowPatterns) {
        if ($title -like "*$pat*") {
          [Microsoft.VisualBasic.Interaction]::AppActivate($w.Current.ProcessId) | Out-Null
          Start-Sleep -Milliseconds 300
          [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
          Write-Info ("  Sent Enter to '" + $title + "'")
          return $true
        }
      }
    }
  }
  return $false
}

# -- Open Compass 0AMV page to trigger background data sync --
function Open-Compass0Amv {
  param([uint32]$ProcessId)
  $hwnd = [Win32C]::FindMainWindow($ProcessId)
  if ($hwnd -eq [IntPtr]::Zero) {
    Write-Info "  Compass main window not found for 0AMV"
    return $false
  }
  [Win32C]::SetForegroundWindow($hwnd) | Out-Null
  Start-Sleep -Seconds 2
  [System.Windows.Forms.SendKeys]::SendWait("0AMV")
  Start-Sleep -Milliseconds 300
  [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
  Start-Sleep -Seconds 5
  Save-Screenshot "compass_0amv"
  Write-Info "  Compass 0AMV page opened"
  return $true
}

# -- UIA helper: detect TDX 'download done' link in download dialog --
function Test-TdxDownloadDone {
  Add-Type -AssemblyName UIAutomationClient -ErrorAction SilentlyContinue
  Add-Type -AssemblyName UIAutomationTypes -ErrorAction SilentlyContinue
  $root = [System.Windows.Automation.AutomationElement]::RootElement
  $condTrue = [System.Windows.Automation.Condition]::TrueCondition
  $allWindows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $condTrue)
  foreach ($w in $allWindows) {
    $title = $w.Current.Name
    if ($title -like "*盘后数据下载*") {
      $nameCond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty, "下载完毕"
      )
      $link = $w.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $nameCond)
      if ($link) { return $true }
    }
  }
  return $false
}

# -- UIA helper: click 'close' button in TDX download dialog --
function Close-TdxDownloadDialog {
  Add-Type -AssemblyName UIAutomationClient -ErrorAction SilentlyContinue
  Add-Type -AssemblyName UIAutomationTypes -ErrorAction SilentlyContinue
  $root = [System.Windows.Automation.AutomationElement]::RootElement
  $condTrue = [System.Windows.Automation.Condition]::TrueCondition
  $allWindows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $condTrue)
  foreach ($w in $allWindows) {
    $title = $w.Current.Name
    if ($title -like "*盘后数据下载*") {
      $nameCond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty, "关闭"
      )
      $btn = $w.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $nameCond)
      if ($btn) {
        try {
          $invoke = $btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
          $invoke.Invoke()
          return $true
        } catch {}
      }
    }
  }
  return $false
}

# -- Trigger TDX .933 download sequence (proven in calibrate_tdx_run.ps1) --
function Trigger-TdxDownload {
  param([IntPtr]$Hwnd)
  Write-Info "  Closing TDX info popup (3x Escape)..."
  Send-TdxKey -Hwnd $Hwnd -Key "{ESC}{ESC}{ESC}" -DelayMs 400
  Start-Sleep -Seconds 1
  Save-Screenshot "tdx_01_after_escape"

  Write-Info "  Opening .933 download dialog..."
  Send-TdxKey -Hwnd $Hwnd -Key ".933" -DelayMs 500
  Send-TdxKey -Hwnd $Hwnd -Key "{ENTER}" -DelayMs 500
  Start-Sleep -Seconds 3
  Save-Screenshot "tdx_02_after_933"

  Write-Info "  Pressing Space to check first checkbox..."
  Send-TdxKey -Hwnd $Hwnd -Key " " -DelayMs 800
  Save-Screenshot "tdx_03_after_space"

  Write-Info "  Pressing Tab*3 + Enter to start download..."
  Send-TdxKey -Hwnd $Hwnd -Key "{TAB}{TAB}{TAB}" -DelayMs 300
  Send-TdxKey -Hwnd $Hwnd -Key "{ENTER}" -DelayMs 500
  Start-Sleep -Seconds 2
  Save-Screenshot "tdx_04_after_enter"

  Write-Info "  TDX download triggered"
}

# -- Step 0: env check --
Write-Step "Check environment"
if (-not (Test-Path $Python)) { Write-Host "ERROR: Python not found: $Python"; exit 1 }
Add-Type -AssemblyName System.Windows.Forms | Out-Null

# -- Step 1: launch data sources --
Write-Step "Launch data software"

$ZnzBefore = if (Test-Path $ZnzData) { (Get-Item $ZnzData).LastWriteTime } else { Get-Date "2000-01-01" }
$TdxBefore = if (Test-Path $TdxData) { (Get-Item $TdxData).LastWriteTime } else { Get-Date "2000-01-01" }

$processes = @()
$znzProc = $null
$tdxProc = $null
$tdxHwnd = [IntPtr]::Zero
$script:Errors = New-Object System.Collections.ArrayList

if (Test-Path $ZnzExe) {
  Write-Info "Starting Compass..."
  $znzProc = Start-Process -FilePath $ZnzExe -WorkingDirectory $ZnzDir -PassThru
  Write-Info ("  PID: " + $znzProc.Id)
  $processes += $znzProc
}
if (Test-Path $TdxExe) {
  Write-Info "Starting TDX..."
  $tdxProc = Start-Process -FilePath $TdxExe -WorkingDirectory $TdxDir -PassThru
  Write-Info ("  PID: " + $tdxProc.Id)
  $processes += $tdxProc
}

if ($processes.Count -eq 0) {
  Write-Host "No data source, run monitor directly"
  & $Python $LiveMonitor
  exit 0
}

# -- Step 2: auto-login + Compass 0AMV (strictly serial before TDX) --
Write-Step "Auto-login + Compass 0AMV (then TDX)"

# Compass first: login, open 0AMV, then close
if ($znzProc) {
  Write-Info "Compass: waiting for login dialog (up to 15s)..."
  $znzDlgHwnd = [IntPtr]::Zero
  for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 1
    $znzDlgHwnd = [Win32C]::FindDialogForPid([uint32]$znzProc.Id)
    if ($znzDlgHwnd -ne [IntPtr]::Zero) { break }
  }
  if ($znzDlgHwnd -ne [IntPtr]::Zero) {
    Write-Info ("  Login dialog HWND: " + $znzDlgHwnd)
    [Win32C]::SetForegroundWindow($znzDlgHwnd) | Out-Null
    Start-Sleep -Milliseconds 500
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
    Write-Info "  Compass login: Enter sent to login dialog"
    Start-Sleep -Seconds 5
  } else {
    Write-Info "  WARNING: Login dialog not found, may already be logged in"
  }

  # Open 0AMV page to trigger background data sync
  Open-Compass0Amv -ProcessId ([uint32]$znzProc.Id)
  Start-Sleep -Seconds 2

  # Close Compass to release focus and ports before TDX starts
  Write-Info "Closing Compass..."
  Stop-Process -Id $znzProc.Id -Force -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 3
}

# TDX second: login + trigger .933 download
if ($tdxProc) {
  Write-Info "TDX: waiting for window to load (10s)..."
  Start-Sleep -Seconds 10
  $tdxHwnd = [Win32C]::FindMainWindow([uint32]$tdxProc.Id)
  Write-Info ("  TDX HWND: " + $tdxHwnd)

  if ($tdxHwnd -ne [IntPtr]::Zero) {
    Write-Info "TDX: sending Enter to login..."
    [Win32C]::SetForegroundWindow($tdxHwnd) | Out-Null
    Start-Sleep -Milliseconds 500
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
    Write-Info "  TDX login: Enter sent"
    Start-Sleep -Seconds 6

    # Trigger .933 download
    Trigger-TdxDownload -Hwnd $tdxHwnd
  } else {
    Write-Info "  TDX HWND not found, skipping download trigger"
    $script:Errors.Add("TDX HWND not found") | Out-Null
  }
}

# -- Step 3: wait for data download (up to 10 minutes) --
Write-Step "Waiting for data download (max 600s)"

$maxWaitSec = 600
$pollInterval = 5
$waited = 0
$znzDone = -not (Test-Path $ZnzExe)
$tdxDone = -not (Test-Path $TdxExe)

while ($waited -lt $maxWaitSec) {
  Start-Sleep -Seconds $pollInterval
  $waited += $pollInterval

  # Compass: check if data file is fresh
  if (-not $znzDone -and (Test-Path $ZnzData)) {
    $mtime = (Get-Item $ZnzData).LastWriteTime
    if ($mtime -gt $ZnzBefore) {
      Write-Info ("Compass data updated (" + $mtime + ")")
      $znzDone = $true
    }
  }

  # TDX: UIA 'download done' link (primary) OR file mtime (fallback)
  if (-not $tdxDone) {
    if (Test-TdxDownloadDone) {
      Write-Info "TDX download done (UIA 'download done' link detected)"
      $tdxDone = $true
      Close-TdxDownloadDialog | Out-Null
    } elseif ((Test-Path $TdxData)) {
      $mtime = (Get-Item $TdxData).LastWriteTime
      if ($mtime -gt $TdxBefore) {
        Write-Info ("TDX data updated (mtime " + $mtime + ")")
        $tdxDone = $true
      }
    }
  }

  if ($znzDone -and $tdxDone) { break }

  # Progress log every minute
  if (($waited % 60) -eq 0) {
    $compassStatus = if ($znzDone) { "OK" } else { "pending" }
    $tdxStatus = if ($tdxDone) { "OK" } else { "pending" }
    $tdxCur = if (Test-Path $TdxData) { (Get-Item $TdxData).LastWriteTime.ToString("HH:mm:ss") } else { "n/a" }
    Write-Info ("  ...waited " + $waited + "s (Compass:" + $compassStatus + ", TDX:" + $tdxStatus + ", sh000001 mtime:" + $tdxCur + ")")
  }
}

Write-Info ("Wait done (" + $waited + "s)")

# Record errors (no push here; consolidated at end)
if ((Test-Path $TdxExe) -and -not $tdxDone) {
  Write-Output "  TDX download TIMEOUT after ${maxWaitSec}s"
  $script:Errors.Add("TDX download timeout after ${maxWaitSec}s") | Out-Null
}
if ((Test-Path $ZnzExe) -and -not $znzDone) {
  Write-Output "  Compass data not updated"
  $script:Errors.Add("Compass day.vdat stale (not updated in ${maxWaitSec}s)") | Out-Null
}

# close software (Compass already closed in Step 2; just close TDX)
Write-Info "Closing TDX..."
if ($tdxProc) {
  Stop-Process -Id $tdxProc.Id -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 3

# -- Step 4: extract data --
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

# -- Step 5: run monitor with --no-push (PS takes over push) --
Write-Step "Run live monitor"
& $Python $LiveMonitor --no-push
$monitorExit = $LASTEXITCODE
if ($monitorExit -ne 0) {
  $script:Errors.Add("monitor exited with code $monitorExit") | Out-Null
}

# -- Send-FinalReport: ONE consolidated push max --
function Send-FinalReport {
  $statePath = Join-Path $Root "live\state.json"
  $action = "WAIT"
  $state = $null
  if (Test-Path $statePath) {
    try {
      $state = Get-Content $statePath -Raw | ConvertFrom-Json
      $action = $state.last_action
    } catch {}
  }
  $isSignal = $action -in @("LONG_SIGNAL","REDUCE","SHORT_CLEAR","ANCHOR_BREAK_CLEAR")
  $hasError = $script:Errors.Count -gt 0

  if (-not $isSignal -and -not $hasError) {
    Write-Info "No push needed (clean WAIT day, no errors)"
    return
  }

  $title = if ($isSignal) { "AMV signal: $action" } else { "AMV issue" }
  $content = ""
  if ($isSignal) {
    $content += "Action: $action`n"
    if ($state -and $state.current_etf) { $content += "ETF: $($state.current_etf)`n" }
    if ($state -and $state.target_weight) { $content += "Weight: $($state.target_weight)`n" }
  }
  if ($hasError) {
    if ($content) { $content += "`n" }
    $content += "Data issues:`n"
    foreach ($err in $script:Errors) {
      $content += "  - $err`n"
    }
    $content += "Monitor ran with stale data, please check."
  }
  Send-WeChatNotice -Title $title -Content $content
}
Send-FinalReport

Write-Output "DONE"
