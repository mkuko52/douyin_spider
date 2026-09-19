"""check_data_interfaces.py —— 一键实测 6 个数据接口的可用性。

走的是**各项目的真实交付入口**（`<project>/main.py ... --json-out`），不是另写一份请求逻辑，
所以测出来的结果就是接口真实能不能用。

用法（在 `signing/` 目录下）：

    # 1) 先备好一份「活着的 www 登录态」cookie，然后：
    python check_data_interfaces.py --cookie-file comment_reply/js_reverse_cache/private/browser_state.json

    # 只测公开接口（跳过需要登录的 search / 需要 nv8 的 replies）：
    python check_data_interfaces.py --cookie-file <ck> --skip search,replies

    # 指定签名来源覆盖（默认走各项目自己的默认值：replies=nv8，其余=modjs）：
    python check_data_interfaces.py --cookie-file <ck> --abogus-source nv8

前置：
- `replies` 需要真 bdms：先把常驻服务起了（`_shared/start_nv8_service.bat`）；
  没起也能跑，只是每个 replies 调用多 ~5s（自动回落本进程起 Node）。
- `search` 需要**真 www 登录态**（未登录会回 2483，本脚本会如实标出来）。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent          # signing/
AWEME = "7626316866109066511"
COMMENT = "7626681743785050939"
SEC_UID = "MS4wLjABAAAApBXenoFyCKJlEi9DItxR21JPOlhmiGbMiRGugv4aPbZxc6615SAQ7kctt1Lhq_Qa"

# (显示名, 项目目录, 业务参数, 是否需登录态)
CASES = [
    ("视频详情", "aweme_detail",  ["--aweme-id", AWEME], True),
    ("评论列表", "comment_list",  ["--aweme-id", AWEME, "--count", "3"], True),
    ("评论回复", "comment_reply", ["--aweme-id", AWEME, "--comment-id", COMMENT, "--count", "3"], True),
    ("视频列表", "aweme_feed",    ["--count", "3"], True),
    ("用户信息", "user_profile",  ["--sec-user-id", SEC_UID], True),
    ("关键词搜索", "aweme_search", ["--keyword", "minecraft", "--count", "3"], True),
]


def _lst(value) -> list:
    return value if isinstance(value, list) else []


def summarize(name: str, body: dict) -> str:
    """从**拖音原始响应**里抽一行摘要（不是后端 normalize 后的形状）。"""
    if name == "评论列表":
        return f"total={body.get('total')} 本页{len(_lst(body.get('comments')))}"
    if name == "评论回复":
        return f"本页{len(_lst(body.get('comments')))} has_more={body.get('has_more')}"
    if name in ("视频列表", "关键词搜索"):
        items = _lst(body.get("aweme_list")) or _lst(body.get("data"))
        return f"n={len(items)}"
    if name == "用户信息":
        user = body.get("user") if isinstance(body.get("user"), dict) else {}
        return f"{user.get('nickname')} 粉丝={user.get('follower_count')}"
    if name == "视频详情":
        d = body.get("aweme_detail") if isinstance(body.get("aweme_detail"), dict) else {}
        return (d.get("desc") or "")[:24]
    return ""


def run_case(name: str, project: str, args: list, cookie: str, py: str,
             check_login: bool, abogus: str | None, timeout: int) -> dict:
    cmd = [py, str(ROOT / project / "main.py"), *args, "--cookie-file", cookie]
    if check_login:
        cmd.append("--check-login")
    if abogus:
        cmd += ["--abogus-source", abogus]

    out = str(Path(tempfile.mkdtemp(prefix=f"chk_{project}_")) / "out.json")
    cmd += ["--json-out", out]

    t0 = time.time()
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    ms = (time.time() - t0) * 1000
    snapshot: dict = {}
    if Path(out).exists():
        try:
            snapshot = json.loads(Path(out).read_text(encoding="utf-8"))
        finally:
            Path(out).unlink(missing_ok=True)

    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0 and "NEED_LOGIN" in stderr:
        return {"ok": False, "ms": ms, "note": "未登录/会话过期（401）", "raw": stderr[-120:]}
    if proc.returncode != 0:
        return {"ok": False, "ms": ms, "note": f"运行失败 exit={proc.returncode}", "raw": stderr[-160:]}

    body = snapshot.get("json")
    if not isinstance(body, dict):
        return {"ok": False, "ms": ms, "note": f"非 JSON 响应（{snapshot.get('content_type', '?')}）",
                "raw": (snapshot.get("text") or "")[:80] or "空 body"}
    code = body.get("status_code")
    if code == 0:
        return {"ok": True, "ms": ms, "note": summarize(name, body), "raw": ""}
    return {"ok": False, "ms": ms, "note": f"业务失败 status_code={code}",
            "raw": body.get("status_msg") or ""}


def main() -> int:
    ap = argparse.ArgumentParser(description="一键实测 6 个数据接口（走各项目交付入口）")
    ap.add_argument("--cookie-file", required=True, help="活着的 www 登录态 cookie（4 种写法都认）")
    ap.add_argument("--python", default=sys.executable, help="用哪个解释器跑 main.py")
    ap.add_argument("--timeout", type=int, default=120, help="单个接口超时秒数")
    ap.add_argument("--skip", default="", help="逗号分隔，跳过某些项，如 search,replies")
    ap.add_argument("--no-check-login", action="store_true", help="不带 --check-login（不预检登录态）")
    ap.add_argument("--abogus-source", choices=("modjs", "nv8"), default=None,
                    help="覆盖所有项目的 a_bogus 来源（默认用各项目自己的默认值）")
    args = ap.parse_args()

    if not Path(args.cookie_file).exists():
        print(f"cookie 文件不存在：{args.cookie_file}", file=sys.stderr)
        return 2

    # --skip 用中文名或项目名都认
    skips = {s.strip() for s in args.skip.split(",") if s.strip()}
    cases = [c for c in CASES if c[0] not in skips and c[1] not in skips
             and c[1].replace("aweme_", "").replace("comment_", "") not in skips]

    print(f"cookie : {args.cookie_file}")
    print(f"python : {args.python}")
    print(f"来源   : {args.abogus_source or '各项目默认（replies=nv8，其余=modjs）'}")
    print("-" * 78)

    results = []
    for name, project, sub, need_login in cases:
        try:
            r = run_case(name, project, sub, args.cookie_file, args.python,
                         need_login and not args.no_check_login, args.abogus_source, args.timeout)
        except subprocess.TimeoutExpired:
            r = {"ok": False, "ms": args.timeout * 1000, "note": f"超时（{args.timeout}s）", "raw": ""}
        results.append((name, r))
        flag = "✅" if r["ok"] else "❌"
        print(f"{flag} {name:<6} {r['ms']:7.0f}ms  {r['note']}")
        if r["raw"]:
            print(f"          ↳ {r['raw']}")

    ok = sum(1 for _, r in results if r["ok"])
    print("-" * 78)
    print(f"通过 {ok}/{len(results)}")
    if not args.abogus_source and any(n == "评论回复" for n, _ in results):
        print("提示：`评论回复` 需真 bdms；若很慢，先起常驻服务 signing/_shared/start_nv8_service.bat")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
