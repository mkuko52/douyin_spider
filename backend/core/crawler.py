"""crawler.py —— 抖音纯协议请求调度（复用 signing/ 两个项目的交付入口 main.py）。

分工：签名项目是唯一 HTTP 出口（参数/签名/会话引导/发请求都在它们内部完成），
backend 只做「调度 + 会话与登录态缓存」。

为什么是 subprocess 而不是 import：
- `signing/send_code` 与 `signing/sms_login` 各有自己的 venv / 依赖 / 常驻 Node(nv8) /
  浏览器工件，且真实场景里它们是**分开的两个项目**；
- 两个项目都有同名 `utils` 包，同进程 import 会互相覆盖。

依据（只看交付物与逆向报告，不依赖任何测试脚本）：
- `signing/send_code/README.md` + `分析报告.md`：发码只在 `--abogus-source service/browser`
  上成功；`artifact_service` 的 `/cookies` 自我说明为「调用方必须用**同一会话**的 cookie
  去发请求，不能另建会话自己取 cookie」（a_bogus 绑在浏览器会话/设备上）。
- `signing/sms_login/README.md` §7 + `分析报告.md` §6.8：登录沿用同一会话能明显降风控
  （新 ttwid = 新设备身份，易被判 `7 访问太频繁`）；`7/2156` 是风控而非参数错误，
  与请求者/会话强相关（实测 62s 提交也能成功，所以**不做时间门禁**）。

响应契约（已按真实响应归一化，见 `tests/test_crawler_offline.py`）：
    send_code  -> {success, message, error_code, captcha, mobile_ticket, retry_after}
    sms_login  -> {success, message, error_code, cookies, session_id, user_id}
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional
from urllib.error import URLError
from urllib.request import urlopen

from ..config import settings
from .cache import get_cache

logger = logging.getLogger(__name__)

# 判为「登录态」的 cookie（sms_login 成功时服务端下发，见分析报告第 5 节）
LOGIN_COOKIE_NAMES = (
    "sessionid", "sessionid_ss", "sid_tt", "sid_guard", "uid_tt",
    "x_tt_token", "d_ticket", "passport_mfa_token",
)


class DouyinError(RuntimeError):
    """调用签名项目失败（参数非法 / 进程崩溃 / 超时 / 输出不是 JSON）。"""


def is_success(body: dict) -> bool:
    """抖音 /passport/web/* 的成功判据。

    实测两种成功形态：
      send_code -> {"data": {...}, "message": "success"}
      sms_login -> {"data": {...}, "message": "success"} / data.error_code == 0
    失败形态一律是 {"data": {"error_code": 2156|1203|7, ...}, "message": "error"}。
    """
    data = body.get("data") or {}
    return body.get("message") == "success" or data.get("error_code") == 0


class DouyinCrawler:
    """发码 / 短信登录的调度层。只做「调度 + 会话与登录态缓存」，不自己发抖音请求。"""

    def __init__(self):
        # ponytail: 全局单锁 —— 工件服务只持有一条浏览器会话，并发发码会共用同一设备
        # 身份（直接撞风控）。真要并发就多开服务实例 + 多端口。
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ CLI 调度
    @staticmethod
    def _project_dir(name: str) -> Path:
        directory = Path(settings.SIGNING_DIR) / name
        if not (directory / "main.py").exists():
            raise DouyinError(f"签名项目不存在：{directory}")
        return directory

    @staticmethod
    def _python(directory: Path) -> str:
        """签名项目自己的 venv 优先（依赖齐全），否则退回当前解释器。"""
        if settings.SIGNING_PYTHON:
            return settings.SIGNING_PYTHON
        for rel in ("runtime/venv/Scripts/python.exe", "runtime/venv/bin/python"):
            exe = directory / rel
            if exe.exists():
                return str(exe)
        return sys.executable

    def _run_cli(self, project: str, args: list, timeout: int) -> dict:
        """跑签名项目 main.py，返回它落盘的响应快照（--json-out）。"""
        directory = self._project_dir(project)
        fd, out_path = tempfile.mkstemp(prefix=f"dy_{project}_", suffix=".json")
        os.close(fd)
        cmd = [self._python(directory), str(directory / "main.py"), *args, "--json-out", out_path]
        try:
            proc = subprocess.run(
                cmd, cwd=str(directory), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            if proc.returncode != 0:
                tail = (proc.stderr or proc.stdout or "").strip()[-800:]
                if "--json-out" in tail:
                    # 签名项目的 main.py 被整体改写时最容易丢的就是这个参数
                    raise DouyinError(
                        f"{project}/main.py 不认识 --json-out（被改写/回退过）。"
                        "请恢复该参数（见 android/AGENTS.md「接口契约」），"
                        f"或用 git/备份还原。原始输出：{tail}")
                raise DouyinError(f"{project} 退出码 {proc.returncode}：{tail}")
            return json.loads(Path(out_path).read_text(encoding="utf-8"))
        except subprocess.TimeoutExpired as exc:
            raise DouyinError(f"{project} 超时（{timeout}s）") from exc
        except (OSError, ValueError) as exc:
            raise DouyinError(f"{project} 输出不是合法 JSON：{exc}") from exc
        finally:
            Path(out_path).unlink(missing_ok=True)

    @staticmethod
    def _service_get(path: str, timeout: float = 10.0) -> dict:
        """读发码工件服务（127.0.0.1:8787）的本地端口。"""
        url = settings.ARTIFACT_SERVICE_URL.rstrip("/") + path
        with urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    @staticmethod
    def _validate_phone(phone: str) -> None:
        if not (len(phone) == 11 and phone.isdigit()):
            raise DouyinError("手机号格式不对（应为 11 位数字）")

    # ------------------------------------------------------------------ 发码
    def _send_code_sync(self, phone: str) -> dict:
        payload = self._run_cli(
            "send_code",
            ["--mobile", phone, "--service-url", settings.ARTIFACT_SERVICE_URL],
            settings.SEND_CODE_TIMEOUT,
        )
        body = payload.get("json") or {}
        data = body.get("data") or {}
        result = {
            "success": is_success(body),
            "message": data.get("description") or body.get("message") or "未知响应",
            "error_code": data.get("error_code"),
            "captcha": data.get("captcha") or None,
            "mobile_ticket": data.get("mobile_ticket"),
            "retry_after": data.get("retry_time"),
        }
        if not result["success"]:
            return result

        # 发码那条会话 == 登录那条会话（同一设备身份），否则大概率被判 `7 访问太频繁`
        cache = get_cache()
        try:
            jar = self._service_get("/cookies").get("cookies") or {}
        except (URLError, OSError, ValueError) as exc:
            jar = {}
            logger.warning("取发码会话失败（%s），登录可能被判 7", exc)
        if jar:
            cache.set_json(f"dy_session:{phone}", jar, ttl=settings.SESSION_TTL_SECONDS)
        else:
            logger.warning("未取到发码会话，登录可能被判“访问太频繁”")
        return result

    async def send_code(self, phone: str, captcha: Optional[str] = None) -> dict:
        """发送短信验证码（会给目标号码发**真实短信**）。"""
        self._validate_phone(phone)
        async with self._lock:
            return await asyncio.to_thread(self._send_code_sync, phone)

    # ------------------------------------------------------------------ 登录
    def _sms_login_sync(self, phone: str, code: str) -> dict:
        cache = get_cache()
        jar = cache.get_json(f"dy_session:{phone}")
        fd, cookie_path = tempfile.mkstemp(prefix="dy_cookies_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"jar": jar}, handle)
        try:
            payload = self._run_cli(
                "sms_login",
                ["--mobile", phone, "--code", code,
                 "--cookie-file", cookie_path, "--save-cookies", cookie_path,
                 "--abogus-source", settings.SMS_LOGIN_ABOGUS_SOURCE],
                settings.SMS_LOGIN_TIMEOUT,
            )
            saved = json.loads(Path(cookie_path).read_text(encoding="utf-8")).get("jar") or {}
        finally:
            Path(cookie_path).unlink(missing_ok=True)

        body = payload.get("json") or {}
        data = body.get("data") or {}
        success = is_success(body)
        if success:
            cache.set_json(f"dy_login:{phone}", saved, ttl=settings.SESSION_TTL_SECONDS)
            cache.delete(f"dy_session:{phone}")
        state = {k: v for k, v in saved.items() if k in LOGIN_COOKIE_NAMES}
        uid = data.get("user_id") or data.get("uid")
        return {
            "success": success,
            "message": data.get("description") or body.get("message") or "未知响应",
            "error_code": data.get("error_code"),
            "cookies": state,
            "session_id": state.get("sessionid"),
            "user_id": str(uid) if uid else None,
        }

    async def sms_login(self, phone: str, code: str) -> dict:
        """短信验证码登录；成功返回会话 cookie（登录态）。"""
        self._validate_phone(phone)
        code = (code or "").strip()
        if not code:
            raise DouyinError("验证码不能为空")
        async with self._lock:
            return await asyncio.to_thread(self._sms_login_sync, phone, code)

    # ------------------------------------------------------------------ 登录态
    @staticmethod
    def get_login_state(phone: str) -> dict:
        """读已缓存的登录态 cookie（Phase 2 爬虫要用它）。"""
        return get_cache().get_json(f"dy_login:{phone}")


# 全局实例
_crawler: Optional[DouyinCrawler] = None


def get_crawler() -> DouyinCrawler:
    global _crawler
    if _crawler is None:
        _crawler = DouyinCrawler()
    return _crawler
