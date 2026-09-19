@echo off
REM Start the backend with its own venv (no system python needed).
REM Usage: backend\start.bat [extra uvicorn args, e.g. --reload]
cd /d "%~dp0.."
"%~dp0runtime\venv\Scripts\python.exe" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 %*
