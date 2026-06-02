@echo off
cd /d "%~dp0.."
echo Stopping old dashboard server...
taskkill /F /FI "IMAGENAME eq pythonw.exe" /T 2>nul
taskkill /F /FI "IMAGENAME eq python.exe" /FI "WINDOWTITLE eq server.py" 2>nul
timeout /t 2 /nobreak >nul
echo Starting dashboard server...
start "" ".venv\Scripts\pythonw.exe" "web\server.py"
echo Dashboard server restarted on http://localhost:8000
