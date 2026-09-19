#!/usr/bin/env bash
# 常驻 nv8 工件服务：Node/bdms 只启一次，之后每次 a_bogus 约 50ms
cd "$(dirname "$0")/.."
exec python -m _shared.nv8_service --port 8789
