"""node.py —— 项目自带 Node 的解析（唯一一份）。

解析顺序（不依赖系统 PATH 里恰好有 node）：

1. `DOUYIN_NODE`（显式指定可执行文件）
2. **项目自带** `signing/send_code/runtime/node_local/node(.exe)`
3. `PATH` 上的 `node`

`signer.py`（mod.js 经 execjs）用 `ensure_on_path()` 把自带 node 目录插到 PATH 最前；
`nv8.py` 用 `node_path()` 直接拿可执行文件。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent                      # signing/_shared
BUNDLED_NODE_DIR = ROOT.parent / "send_code" / "runtime" / "node_local"


def node_path() -> str | None:
    """返回 node 可执行文件路径（找不到返回 None）。"""
    explicit = os.environ.get("DOUYIN_NODE", "").strip()
    if explicit and Path(explicit).exists():
        return explicit
    for name in ("node.exe", "node"):
        bundled = BUNDLED_NODE_DIR / name
        if bundled.exists():
            return str(bundled)
    return shutil.which("node")


def ensure_on_path() -> str | None:
    """把自带 node 目录插到 `PATH` 最前（execjs 靠 PATH 找 node）。

    自带 node 不在就原样返回（回落系统 PATH）。返回最终用的 node 路径。
    """
    for name in ("node.exe", "node"):
        bundled = BUNDLED_NODE_DIR / name
        if not bundled.exists():
            continue
        directory = str(BUNDLED_NODE_DIR)
        parts = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
        if not parts or os.path.normcase(parts[0]) != os.path.normcase(directory):
            os.environ["PATH"] = os.pathsep.join([directory] + parts)
        return str(bundled)
    return shutil.which("node")
