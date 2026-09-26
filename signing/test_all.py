"""一键测试 6 个数据接口：复用有效登录态，否则发码并提示输入验证码。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import requests

from _shared import http

ROOT = Path(__file__).resolve().parent
SESSION = ROOT / "sms_login" / "js_reverse_cache" / "private" / "sms_login_session.json"


def logged_in() -> bool:
    if not SESSION.is_file():
        return False
    try:
        jar = http.load_cookie_file(str(SESSION))
        http.silence_tls_warnings()
        http.assert_login("; ".join(f"{k}={v}" for k, v in jar.items()))
        return True
    except (http.LoginRequiredError, requests.RequestException, OSError, ValueError) as exc:
        print(f"现有登录态不可用：{exc}")
        return False


def main() -> int:
    if not logged_in():
        print("需要登录：接下来会发送短信，并提示输入手机号和验证码。", flush=True)
        result = subprocess.run([sys.executable, str(ROOT / "sms_login" / "tests" / "e2e_login.py")],
                                cwd=ROOT / "sms_login")
        if result.returncode:
            return result.returncode
        if not logged_in():
            print("登录未成功，未执行数据接口测试。", file=sys.stderr)
            return 1

    return subprocess.run([sys.executable, str(ROOT / "check_data_interfaces.py"),
                           "--cookie-file", str(SESSION)], cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
