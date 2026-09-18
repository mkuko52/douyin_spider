"""bootstrap.py —— 建项目自带的 Python / Node 运行时（不依赖本机环境变量）。

    runtime\\venv\\Scripts\\python.exe runtime\\bootstrap.py --check      # 只探测
    runtime\\venv\\Scripts\\python.exe runtime\\bootstrap.py --install    # 真正安装

安装内容：
  1. Python 依赖（cryptography / requests）装进 runtime/venv
  2. 把一份 Node（>=18.18，nv8 要求；推荐 22+）落到 runtime/node_local

Node 来源顺序（--node-home 可指定）：
  1. 已有 runtime/node_local
  2. nvm 目录下最高的 v22/v20/v18
  3. PATH 上的 node

Windows 上默认用目录 junction（秒级、不占空间）；其他平台用 symlink；都不行才真复制。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
VENV = RUNTIME / "venv"
NODE_LOCAL = RUNTIME / "node_local"
REQUIREMENTS = ROOT / "requirements.txt"

MIN_NODE = (18, 18)


def python_exe(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def node_exe(base: Path) -> Path:
    for candidate in (base / "node.exe", base / "node", base / "bin" / "node"):
        if candidate.exists():
            return candidate
    return base / "node.exe"


def find_node_base(explicit: str | None) -> Path | None:
    if explicit:
        base = Path(explicit)
        return base if node_exe(base).exists() else None
    if node_exe(NODE_LOCAL).exists():
        return NODE_LOCAL

    roots = [
        os.environ.get("NVM_HOME"),
        os.environ.get("NVM_DIR"),
        str(Path.home() / "AppData" / "Roaming" / "nvm"),
        "/usr/local/nvm",
        "/usr/local",
    ]
    versions: list[Path] = []
    for root in roots:
        if not root:
            continue
        base = Path(root)
        if not base.is_dir():
            continue
        versions += sorted(base.glob("v2[0-9].*"), reverse=True)
    for version in versions:
        if node_exe(version).exists():
            return version

    found = shutil.which("node")
    return Path(found).parent if found else None


def node_version(base: Path) -> tuple[int, int] | None:
    exe = node_exe(base)
    if not exe.exists():
        return None
    try:
        out = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    text = out.stdout.strip().lstrip("v")
    try:
        major, minor = text.split(".")[:2]
        return int(major), int(minor)
    except ValueError:
        return None


def link_node(source: Path) -> str:
    """把 source 变成 runtime/node_local（junction / symlink / 复制）。"""
    if NODE_LOCAL.exists():
        return "已存在：%s" % NODE_LOCAL
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(NODE_LOCAL), str(source)],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return "junction -> %s" % source
    else:
        try:
            NODE_LOCAL.symlink_to(source, target_is_directory=True)
            return "symlink -> %s" % source
        except OSError:
            pass
    shutil.copytree(source, NODE_LOCAL)
    return "已复制 %s" % source


def check() -> int:
    ok = True
    print("== Python ==")
    print("  当前解释器:", sys.executable)
    if python_exe(VENV).exists():
        print("  runtime/venv: OK ->", python_exe(VENV))
    else:
        print("  runtime/venv: 缺失（先跑 --install）")
        ok = False

    print("== Node ==")
    base = find_node_base(None)
    if not base:
        print("  Node: 未找到（--install --node-home <目录> 可指定）")
        return 1
    ver = node_version(base)
    print("  源目录:", base)
    print("  版本:", "v%d.%d" % ver if ver else "?")
    if ver and ver < MIN_NODE:
        print("  版本过低，nv8 要求 >= %d.%d" % MIN_NODE)
        ok = False
    if node_exe(NODE_LOCAL).exists():
        print("  runtime/node_local: OK")
    else:
        print("  runtime/node_local: 缺失（先跑 --install）")
        ok = False
    return 0 if ok else 1


def install(node_home: str | None) -> int:
    RUNTIME.mkdir(parents=True, exist_ok=True)

    if not python_exe(VENV).exists():
        print("[1/3] 创建 venv ...")
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    else:
        print("[1/3] venv 已存在，跳过")

    print("[2/3] 安装 Python 依赖 ...")
    subprocess.run(
        [str(python_exe(VENV)), "-m", "pip", "install", "--disable-pip-version-check",
         "-r", str(REQUIREMENTS)],
        check=True,
    )

    print("[3/3] 布置 Node 运行时 ...")
    base = find_node_base(node_home)
    if not base:
        print("找不到 Node。请用 --node-home 指定 Node 安装目录（含 node.exe）。")
        return 1
    ver = node_version(base)
    if ver and ver < MIN_NODE:
        print("Node 版本 %d.%d 过低，nv8 要求 >= %d.%d" % (*ver, *MIN_NODE))
        return 1
    print("  ", link_node(base))

    print("\n完成。用 runtime\\run.py 执行 main.py。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="建立项目自带的 Python/Node 运行时")
    parser.add_argument("--check", action="store_true", help="只探测，不写入")
    parser.add_argument("--install", action="store_true", help="创建 venv 并安装依赖")
    parser.add_argument("--node-home", help="Node 安装目录（含 node.exe）")
    args = parser.parse_args()

    if args.install:
        return install(args.node_home)
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
