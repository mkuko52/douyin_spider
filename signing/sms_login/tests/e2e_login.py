r"""e2e_login.py —— 跨项目端到端：`send_code` 发码 → 输入验证码 → `sms_login` 登录。

**两个项目在真实场景里是分开的**，所以这里只通过 `subprocess` 调用 `send_code`，
不 import 它的任何模块；`sms_login` 侧也不依赖它。删掉这个文件不影响两个项目的独立运行。

用法（在 sms_login 目录下）：

    # 完整流程：调用 send_code 真发一条短信，然后提示输入验证码并登录
    python tests/e2e_login.py --mobile 138xxxxxxxx

    # 已经收到过验证码：跳过发码，直接登录
    python tests/e2e_login.py --mobile 138xxxxxxxx --skip-send

    # 只验证接线，不发任何真实请求
    python tests/e2e_login.py --mobile 138xxxxxxxx --dry-run

可选参数：
    --code 123456        直接给验证码，不提问
    --send-code-dir DIR  覆盖 send_code 项目路径（默认 ../send_code）
    --session FILE       复用/保存会话 cookie（默认 js_reverse_cache/private/sms_login_session.json）
    --no-session         每次都新引导会话（更容易撞风控，仅诊断用）
    --timeout N          等待 send_code 返回的秒数（默认 300）
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_SEND_CODE_DIR = ROOT.parent / "send_code"
DEFAULT_SESSION = ROOT / "js_reverse_cache" / "private" / "sms_login_session.json"
DEFAULT_SERVICE = "http://127.0.0.1:8787"


def fetch_send_code_session(service_url: str, session_file: pathlib.Path) -> bool:
    """从 send_code 的常驻工件服务拿它**发码时用的那条浏览器会话**。

    为什么必须这样做：实测用“新会话”登录同一个号会得到 `7 访问太频繁`
    （会话/设备级频控）；换成**发码时的那条会话**后立即变回正常业务响应。
    所以“发码会话 == 登录会话”是打通登录的必要条件。

    两个项目依然解耦：这里只是 HTTP 读一个本地端口，不 import send_code 的模块。
    """
    try:
        raw = urllib.request.urlopen(service_url.rstrip("/") + "/cookies", timeout=20).read()
        cookies = json.loads(raw).get("cookies") or {}
    except Exception as exc:
        print("[e2e] 取不到 send_code 会话（%s），回退到本地会话文件：%s" % (exc, session_file))
        return False
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(json.dumps({"jar": cookies}, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    print("[e2e] 已复用发码会话：%d 个 cookie -> %s" % (len(cookies), session_file))
    return True


def send_code_python(send_code_dir: pathlib.Path) -> list[str]:
    """优先用 send_code 自带的 venv（它需要 aiohttp/playwright），否则退回当前解释器。"""
    for rel in ("runtime/venv/Scripts/python.exe", "runtime/venv/bin/python"):
        candidate = send_code_dir / rel
        if candidate.exists():
            return [str(candidate)]
    return [sys.executable]


def run_send_code(send_code_dir: pathlib.Path, mobile: str, timeout: int) -> bool:
    """调 send_code 的 main.py 发一条真实验证码短信（stdio 直通，用户能看到它全部输出）。"""
    entry = send_code_dir / "main.py"
    if not entry.exists():
        print("找不到 %s —— 用 --send-code-dir 指定 send_code 项目路径。" % entry)
        return False
    cmd = send_code_python(send_code_dir) + [str(entry), "--mobile", mobile]
    print("\n" + "=" * 78)
    print("① 调用 send_code 发码：", " ".join(cmd))
    print("=" * 78, flush=True)
    proc = subprocess.run(cmd, cwd=str(send_code_dir), timeout=timeout)
    if proc.returncode != 0:
        print("send_code 退出码 %d（继续，可能你已经收到短信了）" % proc.returncode)
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="send_code → sms_login 端到端连通")
    parser.add_argument("--mobile", help="真实手机号（11 位）；不填则提问")
    parser.add_argument("--code", help="短信验证码；不填则提问")
    parser.add_argument("--skip-send", action="store_true", help="跳过发码，直接登录")
    parser.add_argument("--dry-run", action="store_true", help="不发任何真实请求")
    parser.add_argument("--send-code-dir", default=str(DEFAULT_SEND_CODE_DIR))
    parser.add_argument("--session", default=str(DEFAULT_SESSION),
                        help="复用/保存会话 cookie（凭证，仅本机 private 目录）")
    parser.add_argument("--no-session", action="store_true", help="每次新引导会话（易撞风控）")
    parser.add_argument("--send-code-service", default=DEFAULT_SERVICE,
                        help="send_code 常驻工件服务地址（用它的会话发码/登录，默认 %s）" % DEFAULT_SERVICE)
    parser.add_argument("--timeout", type=int, default=300, help="等待 send_code 的秒数")
    parser.add_argument("--post-send-delay", type=int, default=95,
                        help="发码后等多少秒再登录（默认 95）。实测阈值在 ~90s："
                             "<90s 提交会得到 `7 访问太频繁`，**而且会把该验证码作废**")
    args = parser.parse_args()

    mobile = (args.mobile or "").strip()
    if not mobile:
        try:
            mobile = input("请输入手机号（11 位，不带 +86）：").strip()
        except (EOFError, KeyboardInterrupt):
            print()
    if not (len(mobile) == 11 and mobile.isdigit()):
        print("手机号 %r 格式不对（应为 11 位数字）。" % mobile)
        return 2

    if not args.skip_send and not args.dry_run:
        run_send_code(pathlib.Path(args.send_code_dir), mobile, args.timeout)
        sent_at = time.monotonic()
    else:
        sent_at = None

    # 先拿验证码，再把剩余的时间窗睡完，最后只尝试一次
    code = (args.code or "").strip()
    if not code:
        try:
            code = input("\n② 请输入收到的短信验证码：").strip()
        except (EOFError, KeyboardInterrupt):
            print()
    if not code:
        print("没拿到验证码，退出。")
        return 2

    if sent_at is not None and not args.dry_run:
        remaining = args.post_send_delay - (time.monotonic() - sent_at)
        if remaining > 0:
            print("② 等发码窗口打开（还需 %.0fs，避免 `7 访问太频繁`）…" % remaining, flush=True)
            time.sleep(remaining)

    session_file = pathlib.Path(args.session)
    if not args.no_session and not args.dry_run:
        # 关键：登录必须用**发码那条会话**，否则会得到 `7 访问太频繁`
        fetch_send_code_session(args.send_code_service, session_file)

    # ③ 交给 sms_login 自己的 main.py（两个项目唯一的耦合点就是这行命令行）
    cmd = [sys.executable, str(ROOT / "main.py"), "--mobile", mobile, "--code", code]
    if not args.no_session:
        if session_file.exists():
            cmd += ["--cookie-file", str(session_file)]
            print("③ 复用会话：", session_file)
        cmd += ["--save-cookies", str(session_file)]
    if args.dry_run:
        cmd.append("--dry-run")

    print("\n" + "=" * 78)
    print("③ 调用 sms_login 登录：", " ".join(cmd))
    print("=" * 78, flush=True)
    return subprocess.run(cmd, cwd=str(ROOT)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
