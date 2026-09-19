@echo off
REM Resident artifact service: browser/Node starts once, then each call is millisecond-level.
cd /d "%~dp0"
runtime\venv\Scripts\python.exe -m utils.artifact_service --port 8787
