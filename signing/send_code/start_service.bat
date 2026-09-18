@echo off
REM 常驻「窄工件」服务：浏览器/Node 只启一次，之后每次调用毫秒级
cd /d "%~dp0"
runtime\venv\Scripts\python.exe -m utils.artifact_service --port 8787
