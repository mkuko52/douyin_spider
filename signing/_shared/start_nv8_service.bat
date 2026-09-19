@echo off
REM Resident nv8 artifact service: Node/bdms starts once, then each a_bogus is ~20ms.
REM Data projects use it via --abogus-source nv8; without it they fall back to a per-process Node (~5s).
cd /d "%~dp0.."
python -m _shared.nv8_service --port 8789
