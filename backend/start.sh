#!/usr/bin/env bash
# 用后端自带 venv 起服务（不依赖系统 python）
cd "$(dirname "$0")/.."
PY="backend/runtime/venv/Scripts/python.exe"
[ -x "$PY" ] || PY="backend/runtime/venv/bin/python"
exec "$PY" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 "$@"
