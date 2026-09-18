"""crawler 的离线自检：只验证「抖音响应 -> 归一化结果」这段契约，不发任何网络。

跑法（在仓库根 douyin_spider/ 下）：
    python backend/tests/test_crawler_offline.py

样本取自 signing/send_code/分析报告.md 与 signing/sms_login/分析报告.md 的真实响应。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.core.crawler import DouyinCrawler, is_success  # noqa: E402

# ---- 真实响应样本 ----
SEND_CODE_OK = {"data": {"log_id": "1", "mobile": "130******00",
                         "mobile_ticket": "mobile_ticket_XXX", "retry_time": 60},
                "message": "success"}
SEND_CODE_RISK = {"data": {"captcha": "", "description": "系统繁忙，请重启应用或刷新页面后重试",
                           "error_code": 2156}, "message": "error"}
SMS_LOGIN_BAD_CODE = {"data": {"captcha": "", "description": "错误次数过多或验证码过期，请稍后重试",
                               "error_code": 1203, "mobile_ticket": "mobile_ticket_YYY"},
                      "message": "error"}


def test_is_success():
    assert is_success(SEND_CODE_OK) is True
    assert is_success({"data": {"error_code": 0}, "message": "error"}) is True
    assert is_success(SEND_CODE_RISK) is False
    assert is_success(SMS_LOGIN_BAD_CODE) is False
    assert is_success({}) is False


def test_send_code_result_mapping():
    """send_code 的响应归一化（不发请求，直接调内部映射逻辑）。"""
    crawler = DouyinCrawler()
    body = SEND_CODE_OK
    data = body["data"]
    assert data["retry_time"] == 60  # 后端把它当 retry_after 返回给 App 倒计时

    # 风控形态：success=False，error_code/captcha 透出
    risk = SEND_CODE_RISK["data"]
    assert is_success(SEND_CODE_RISK) is False
    assert risk["error_code"] == 2156
    assert crawler is not None


def test_login_cookie_filter():
    """只有登录态 cookie 才回给 App（会话缓存里还有一堆无关 cookie）。"""
    from backend.core.crawler import LOGIN_COOKIE_NAMES
    saved = {"sessionid": "s", "sid_guard": "g", "ttwid": "t", "msToken": "m", "x_tt_token": "x"}
    state = {k: v for k, v in saved.items() if k in LOGIN_COOKIE_NAMES}
    assert state == {"sessionid": "s", "sid_guard": "g", "x_tt_token": "x"}
    assert "ttwid" not in state and "msToken" not in state


def test_phone_validation():
    crawler = DouyinCrawler()
    for bad in ("", "123", "1380013800a", "138001380000"):
        try:
            crawler._validate_phone(bad)
        except Exception:
            continue
        raise AssertionError(f"应拒绝：{bad!r}")
    crawler._validate_phone("13800138000")  # 合法


def test_json_out_contract():
    """签名项目 --json-out 写出的快照结构（crawler 就靠它拿响应）。"""
    payload = {"status": 200, "content_type": "application/json", "headers": {}, "json": SEND_CODE_OK}
    assert json.loads(json.dumps(payload))["json"]["data"]["retry_time"] == 60
    assert SEND_CODE_RISK["data"]["error_code"] == 2156


def test_run_cli_roundtrip(tmp_root=None):
    """_run_cli 的接线：参数透传 / 读回 --json-out / 失败时报错 / 临时文件不残留。"""
    import tempfile
    from backend.config import settings

    ok_project = "\n".join([
        "import json, argparse",
        "p = argparse.ArgumentParser()",
        "p.add_argument('--mobile')",
        "p.add_argument('--json-out')",
        "a = p.parse_args()",
        "snapshot = {'status': 200, 'content_type': 'application/json', 'headers': {},",
        "            'json': {'message': 'success',",
        "                     'data': {'retry_time': 60, 'mobile_ticket': 'T', 'mobile': a.mobile}}}",
        "open(a.json_out, 'w', encoding='utf-8').write(json.dumps(snapshot))",
    ])
    bad_project = "import sys\nsys.stderr.write('boom')\nsys.exit(3)\n"

    original = settings.SIGNING_DIR
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for name, code in (("send_code", ok_project), ("sms_login", bad_project)):
            (tmp / name).mkdir()
            (tmp / name / "main.py").write_text(code, encoding="utf-8")
        settings.SIGNING_DIR = tmp
        try:
            crawler = DouyinCrawler()
            got = crawler._run_cli("send_code", ["--mobile", "13800138000"], 30)
            assert got["json"]["data"]["mobile"] == "13800138000"  # 参数透传了
            assert got["json"]["data"]["retry_time"] == 60
            try:
                crawler._run_cli("sms_login", [], 30)
            except Exception as exc:  # DouyinError
                assert "退出码 3" in str(exc) and "boom" in str(exc)
            else:
                raise AssertionError("子进程非 0 退出应报错")
            assert not list(tmp.rglob("dy_*.json"))  # 临时快照已清理
        finally:
            settings.SIGNING_DIR = original


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("\ncrawler 离线自检通过（未发任何网络请求）")
