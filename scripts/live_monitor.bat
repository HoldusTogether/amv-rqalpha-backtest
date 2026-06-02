@echo off
chcp 65001 >nul
cd /d "%~dp0.."
call .venv\Scripts\python.exe live\live_monitor.py %*
if %ERRORLEVEL% neq 0 (
  echo.
  echo 按任意键退出...
  pause >nul
)
