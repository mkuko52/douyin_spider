"""cli.py —— 数据接口共用的命令行样板（唯一一份）。

`build_parser` 提供各接口通用的 7 个开关；`prepare` 解析出 cookie 串与 TLS 校验开关，
并在 `--check-login` 时先确认会话是 `www.douyin.com` 登录态。
接口自己的参数（`--aweme-id` 等）由各 `main.py` 在 `build_parser` 之后自行 `add_argument`。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import http
from .logger import logger


def build_parser(description: str, root: Path,
                 default_abogus: str = "modjs") -> argparse.ArgumentParser:
    """通用参数（每个数据接口 main.py 都用同一份）。

    `default_abogus`：a_bogus 来源默认值。`replies` 端点必须 `nv8`（见 nv8.py）。
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--cookie-file", help="cookie 文件（storage_state / JSON / `k=v; k=v`）")
    parser.add_argument("--dry-run", action="store_true", help="只组参数与签名，不发请求")
    parser.add_argument("--verbose", action="store_true", help="打印完整 URL")
    parser.add_argument("--verify-tls", action="store_true",
                        help="严格校验 TLS（默认关闭，兼容本机 MITM 代理）")
    parser.add_argument("--check-login", action="store_true",
                        help="发请求前先确认会话是 www.douyin.com 登录态；"
                             "否则打 NEED_LOGIN 到 stderr 并以退出码 3 结束（后端据此回 401）")
    parser.add_argument("--abogus-source", choices=("modjs", "nv8"), default=default_abogus,
                        help="a_bogus 来源：modjs=公开移植版（快，默认）；"
                             "nv8=真 bdms（慢，replies 必须用它）")
    parser.add_argument("--config", default=str(Path(root) / "config.local.json"))
    parser.add_argument("--json-out", help="把响应写成 JSON 文件（后端调度用）")
    return parser


def prepare(args) -> tuple[str, bool]:
    """返回 (cookie 串, verify)。命令行 > config.local.json。

    `--check-login` 时先打 `/aweme/v1/web/notice/count/`：`status_code != 0`（未登录/会话过期）
    就 `NEED_LOGIN` + 退出码 3 —— 后端 `_run_cli` 把它映射成 `DouyinAuthError`（HTTP 401）。
    """
    config = http.load_config(Path(args.config))
    cookie_file = args.cookie_file or config.get("cookie_file")
    verify = bool(args.verify_tls or config.get("verify_tls"))
    if not verify:
        http.silence_tls_warnings()
    jar = http.load_cookie_file(cookie_file) if cookie_file else {}
    if not jar:
        logger.warning("未提供 cookie：多数数据接口会返回 200 + text/plain 空 body（被挡）")
    cookie = "; ".join(f"{k}={v}" for k, v in jar.items())

    if getattr(args, "check_login", False):
        try:
            http.assert_login(cookie, verify)
        except http.LoginRequiredError as exc:
            print(f"NEED_LOGIN: {exc}", file=sys.stderr)
            raise SystemExit(3)
    return cookie, verify
