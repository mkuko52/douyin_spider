"""_common.py —— end_test 共用助手（后端地址 + JWT + POST/打印）。

所有 `*_test.py` 都长一个样：

    from _common import post
    post('/api/data/detail', {'aweme_id': '...'})

做的事：
- `POST {DY_API}{path}`（默认 `http://127.0.0.1:8000`）；
- 有 token 就带 `Authorization: Bearer <token>`（登录类接口不需要，没有就不带）；
- 打印 `HTTP 状态码` + 响应 JSON；
- **响应里有 `token` 就自动写进 `token.txt`**（`login_test.py` 靠这个给数据接口测试供 token）；
- 401 时给排查提示。

token 来源（按顺序）：环境变量 `DY_TOKEN` → 本目录 `token.txt`
（`login_test.py` 会自动生成/覆盖 `token.txt`）。

⚠️ 数据接口（`/api/data/*`）需要「活着的 www 登录态」：若 401 `会话不是有效的 www 登录态`，
   重新登录一次（抖音同账号再登录会让旧会话失效，旧的 token.txt 也会失效）。
   排查见 `signing/接口自测指南.md`。
"""

from __future__ import annotations

import os
from pathlib import Path

import requests

BASE = os.environ.get("DY_API", "http://127.0.0.1:8000").rstrip("/")
TOKEN_FILE = Path(__file__).resolve().with_name("token.txt")


def token() -> str:
    """当前 token（没有则返回空串）。"""
    value = os.environ.get("DY_TOKEN", "").strip()
    if not value and TOKEN_FILE.exists():
        value = TOKEN_FILE.read_text(encoding="utf-8").strip()
    return value


def post(path: str, payload: dict, timeout: int = 120) -> dict:
    """POST 到后端并打印结果，返回解析后的 body。"""
    current = token()
    headers = {"Content-Type": "application/json"}
    if current:
        headers["Authorization"] = "Bearer " + current

    response = requests.post(BASE + path, headers=headers, json=payload, timeout=timeout)
    try:
        body = response.json()
    except ValueError:
        body = {"__raw__": response.text[:300]}

    print(f"{path}  ->  HTTP {response.status_code}")
    print(body)

    # 登录成功 → 顺手把 token 存下来，供数据接口测试用
    if isinstance(body, dict) and body.get("token"):
        TOKEN_FILE.write_text(body["token"], encoding="utf-8")
        print(f"-> token 已写入 {TOKEN_FILE}")

    if response.status_code == 401:
        if not current:
            print(f"\n提示：没有 token。先跑 login_test.py（会自动生成 {TOKEN_FILE.name}），"
                  f"或设环境变量 DY_TOKEN=<登录返回的 token>。")
        else:
            print("\n提示：401 = token 过期 / 会话不是 www 登录态（过期或非 www 登录）。"
                  "\n      重新登录一次再试；同账号再登录会让旧会话失效。")
    return body
