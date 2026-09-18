"""run.py —— 用项目自带运行时执行 main.py（不依赖本机 PATH / 环境变量）。

    runtime\\venv\\Scripts\\python.exe runtime\\run.py --dry-run
    runtime\\venv\\Scripts\\python.exe runtime\\run.py --mobile 138xxxxxxxx --confirm

做的事：
  1. 把 runtime/node_local 放到 PATH 最前（Node 参数服务用）
  2. 用 runtime/venv 的 Python 执行 main.py，并透传所有参数
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
VENV = RUNTIME / "venv"
NODE_LOCAL = RUNTIME / "node_local"


def python_exe() -> Path:
    if os.name == "nt":
        candidate = VENV / "Scripts" / "python.exe"
    else:
        candidate = VENV / "bin" / "python"
    return candidate if candidate.exists() else Path(sys.executable)


def node_exe() -> Path | None:
    for candidate in (NODE_LOCAL / "node.exe", NODE_LOCAL / "node", NODE_LOCAL / "bin" / "node"):
        if candidate.exists():
            return candidate
    return None


def main() -> int:
    env = dict(os.environ)
    node = node_exe()
    if node:
        env["SIGNER_NODE"] = str(node)
        env["PATH"] = os.pathsep.join([str(node.parent), env.get("PATH", "")])
    else:
        print("[warn] 未找到 runtime/node_local/node.exe，请先跑 runtime/bootstrap.py --install")

    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONPATH", str(ROOT))
    return subprocess.call([str(python_exe()), str(ROOT / "main.py"), *sys.argv[1:]], env=env, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
