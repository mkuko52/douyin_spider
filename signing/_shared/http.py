"""http.py —— 数据接口共用的 cookie / 请求 / 落盘工具（唯一一份）。

`main.py` 只负责「接口路径 + 业务参数 + 打印摘要」，其余都在这里：

    cookie, verify = cli.prepare(args)                 # 见 cli.py
    signed = http.sign(PATH, params)                   # 组 URL + a_bogus
    http.dump_request(ROOT, signed)                    # output/last_request.json
    resp, parsed = http.request(signed, cookie, referer, verify)
    http.write_json_out(args.json_out, PATH, resp, parsed)
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

import requests

from . import params as P
from .logger import logger
from .signer import sign_url


def load_cookie_file(path: str) -> dict:
    """支持 storage_state(`{"cookies":[...]}`) / `{"jar":…}` / 普通 JSON / `k=v; k=v` 四种写法。"""
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        return {}
    jar: dict[str, str] = {}
    if text.startswith("{"):
        data = json.loads(text)
        if "cookies" in data:
            for item in data["cookies"]:
                name, domain = item.get("name"), item.get("domain") or ""
                if not name:
                    continue
                if "douyin" not in domain and not domain.endswith("bytedance.com"):
                    continue
                jar[name] = item.get("value", "")
        else:
            jar = dict(data.get("jar") or data)
    else:
        for part in text.replace("\n", ";").split(";"):
            if "=" in part:
                key, _, value = part.partition("=")
                jar[key.strip()] = value.strip()
    logger.info("从 %s 载入 %d 个 cookie", path, len(jar))
    return jar


def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError) as exc:
        logger.warning("config 解析失败（忽略）: %s", exc)
        return {}


def silence_tls_warnings() -> None:
    requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]


def build_headers(cookie: str, referer: str) -> dict:
    return {
        "User-Agent": P.UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": referer,
        "Origin": "https://www.douyin.com",
        "sec-ch-ua": '"Google Chrome";v="151", "Not=A?Brand";v="99", "Chromium";v="151"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "cookie": cookie,
    }


def sign(path: str, params: dict, abogus_source: str = "modjs") -> str:
    """组 URL + 追加 a_bogus（不发请求）。

    `abogus_source`：
    - `modjs`（默认）：公开移植版 `node/mod.js`，快（~0.5s），
      `detail` / `comments` / `feed` / `user` / `search` 都够；
    - `nv8`：真 bdms 字节码（慢，冷启动 ~5s），**`replies` 端点只有这个能过**
      （实测：mod.js a_bogus → `text/plain` 空 body；nv8 → `status_code=0`）。
    """
    url = P.build_url(path, params)
    if abogus_source == "nv8":
        from . import nv8
        return f"{url}&a_bogus={quote(nv8.a_bogus(url, 'GET'), safe='')}"
    return sign_url(url)


# --------------------------------------------------------------- 登录态检查
# `GET /aweme/v1/web/notice/count/`：`status_code=0` = www 已登录；`8` = 未登录/会话过期。
PATH_LOGIN_CHECK = "/aweme/v1/web/notice/count/"


class LoginRequiredError(RuntimeError):
    """会话不是 `www.douyin.com` 登录态（过期 / 未登录）。"""

    def __init__(self, status_code=None):
        self.status_code = status_code
        super().__init__(f"会话不是有效的 www 登录态（status_code={status_code}），请重新登录")


def is_logged_in(body) -> bool:
    """登录判定：拖音业务 `status_code == 0` 即 www 已登录（`8` 未登录）。"""
    return isinstance(body, dict) and body.get("status_code") == 0


def assert_login(cookie: str, verify: bool = False) -> None:
    """确认会话是 www 登录态，不是就抛 `LoginRequiredError`。"""
    signed = sign(PATH_LOGIN_CHECK, {})
    _, parsed = request(signed, cookie, "https://www.douyin.com/", verify)
    status = (parsed or {}).get("status_code")
    logger.info("登录检查 : %s -> %s", PATH_LOGIN_CHECK, "已登录" if is_logged_in(parsed) else "未登录/会话过期")
    if not is_logged_in(parsed):
        raise LoginRequiredError(status)


def request(signed_url: str, cookie: str, referer: str, verify: bool = False,
            extra_headers: dict | None = None):
    """GET 已签名的 URL，返回 (response, parsed_json|None)。"""
    resp = requests.get(signed_url, headers={**build_headers(cookie, referer), **(extra_headers or {})},
                         timeout=25, verify=verify)
    try:
        parsed = resp.json()
    except ValueError:
        parsed = None
    return resp, parsed


def dump_request(root: Path, signed_url: str) -> None:
    """把本次构造的 URL 落盘（output/last_request.json）。"""
    out = Path(root) / "output" / "last_request.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"url": signed_url}, ensure_ascii=False, indent=2),
                   encoding="utf-8")


def write_json_out(out_path: str, path: str, resp, parsed) -> None:
    """后端调度契约：`{path, status, content_type, headers, json}`（非 JSON 时给 `text`）。"""
    text = resp.text
    Path(out_path).write_text(json.dumps({
        "path": path,
        "status": resp.status_code,
        "content_type": resp.headers.get("content-type", ""),
        "headers": dict(resp.headers),
        "json": parsed,
        **({"text": text[:4000]} if parsed is None else {}),
    }, ensure_ascii=False), encoding="utf-8")
