@echo off
cd /d "%~dp0.."
start "" ".venv\Scripts\pythonw.exe" "web\server.py"
echo Dashboard server started on http://localhost:8000
echo (runs in background, no console window)
echo To stop: taskkill /F /IM pythonw.exe
