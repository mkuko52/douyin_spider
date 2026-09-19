"""bootstrap.py —— 建后端自带 venv 并装依赖（跨平台，可重建）。

    python backend/runtime/bootstrap.py --check      # 只探测，无副作用
    python backend/runtime/bootstrap.py --install    # 建 venv + pip install -r backend/requirements.txt

为什么要它：后端自带 venv（`backend/runtime/venv`）有两个作用 ——
1. 跑自己（fastapi/uvicorn/...）；
2. 当**没有自带 venv 的签名项目**的解释器（`crawler._python()` 找不到项目 venv 时回落
   `sys.executable`），所以也装了 requests / cryptography / pyexecjs2 / aiohttp。

Node 不用管：数据项目经 `_shared/node.py` 优先用 `signing/send_code/runtime/node_local` 里的 node。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import venv
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]           # backend/
ROOT = BACKEND.parent                                   # 仓库根
VENV = BACKEND / "runtime" / "venv"
REQUIREMENTS = BACKEND / "requirements.txt"


def venv_python() -> Path:
    win = VENV / "Scripts" / "python.exe"
    return win if win.exists() else VENV / "bin" / "python"


def probe() -> int:
    print(f"venv      : {VENV}  ({'存在' if VENV.exists() else '不存在'})")
    if not venv_python().exists():
        print("  -> 用 `--install` 建 venv")
        return 1
    code = ("import fastapi, uvicorn, jwt, pydantic, aiohttp, requests, cryptography, execjs;"
            "print('  -> 依赖齐全:', fastapi.__version__, uvicorn.__version__)")
    proc = subprocess.run([str(venv_python()), "-c", code], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    print(proc.stdout.strip() or proc.stderr.strip()[-200:])
    return proc.returncode


def install() -> int:
    if not venv_python().exists():
        print(f"[bootstrap] 建 venv -> {VENV}")
        venv.EnvBuilder(with_pip=True).create(str(VENV))
    py = str(venv_python())
    for args in (["-m", "pip", "install", "-q", "--upgrade", "pip"],
                 ["-m", "pip", "install", "-r", str(REQUIREMENTS)]):
        print(f"[bootstrap] {py} {' '.join(args)}")
        proc = subprocess.run([py, *args], cwd=str(ROOT))
        if proc.returncode != 0:
            print("[bootstrap] 失败", file=sys.stderr)
            return proc.returncode
    print("[bootstrap] 完成。起后端：backend/start.bat（或 backend/start.sh）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="后端自带 venv 引导")
    ap.add_argument("--check", action="store_true", help="只探测（默认）")
    ap.add_argument("--install", action="store_true", help="建 venv + pip install")
    args = ap.parse_args()
    return install() if args.install else probe()


if __name__ == "__main__":
    raise SystemExit(main())
