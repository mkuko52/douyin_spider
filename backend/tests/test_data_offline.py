"""数据接口（Phase 2）的离线自检：验证「签名项目 --json-out -> 归一化响应」这段契约。

**不发任何网络**：用 6 个假的 signing 项目（写死快照）验证 crawler 的调度接线
（项目名 / 参数透传 / `--cookie-file` 会话 / `--json-out` 读回），
再用真实响应样本验证 `normalize` 与 `_envelope`。

跑法（在仓库根 douyin_spider/ 下）：
    python backend/tests/test_data_offline.py
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.config import settings                      # noqa: E402
from backend.core import normalize                       # noqa: E402
from backend.core.cache import get_cache                 # noqa: E402
from backend.core.crawler import (  # noqa: E402
    DouyinAuthError,
    DouyinCrawler,
    DouyinError,
)

PHONE = "13800138000"
TTWID = "ttwid_TEST"

# ------------------------------------------------------------------ 样本
AWEME = {
    "aweme_id": "7626316866109066511", "desc": "MC生存", "create_time": 1780000000,
    "aweme_type": 0, "author": {"uid": "1", "sec_uid": "MS4wSEC", "nickname": "傲安",
                                "unique_id": "24784694352"},
    "statistics": {"digg_count": 23603, "comment_count": 10399, "share_count": 1292},
    "video": {"duration": 60000}, "images": None,
}
COMMENT = {
    "cid": "7673750309165007665", "text": "nice", "create_time": 1780000001,
    "digg_count": 3, "ip_label": "广东", "comment_reply_total": 2,
    "user": {"uid": "2", "sec_uid": "MS4wU2", "nickname": "用户A", "unique_id": "u2"},
}
USER = {
    "uid": "1", "sec_uid": "MS4wSEC", "nickname": "傲安", "unique_id": "24784694352",
    "signature": "sig", "follower_count": 1774701, "following_count": 305,
    "total_favorited": 9504386, "aweme_count": 1821,
    "avatar_larger": {"url_list": ["https://x/a.jpeg"]},
}

# 6 个假项目：按自己的目录名返回该接口形状的快照（并把 cookie 里的 ttwid 回显出来）
FAKE_MAIN = '''
import argparse, json
from pathlib import Path
project = Path(__file__).resolve().parent.name
p = argparse.ArgumentParser()
for a in ("--aweme-id", "--comment-id", "--cursor", "--count", "--refresh-index",
          "--sec-user-id", "--keyword", "--offset", "--cookie-file", "--json-out"):
    p.add_argument(a)
p.add_argument("--check-login", action="store_true")
args, _ = p.parse_known_args()
jar = json.load(open(args.cookie_file, encoding="utf-8"))["jar"]
author = {"uid": "1", "sec_uid": jar.get("ttwid", ""), "nickname": "n", "unique_id": "u"}
flag = "check_login=%s" % args.check_login
shape = {
    "aweme_detail": {"aweme_detail": {"aweme_id": args.aweme_id, "desc": flag,
                                      "author": author, "statistics": {"digg_count": 9}}},
    "comment_list": {"comments": [{"cid": "c1", "text": flag, "user": author}],
                     "total": 1, "has_more": 0, "cursor": 1},
    "comment_reply": {"comments": [{"cid": "c2", "text": flag, "user": author}], "has_more": 0},
    "aweme_feed": {"aweme_list": [{"aweme_id": "a1", "desc": flag, "author": author}],
                   "has_more": 1},
    "user_profile": {"user": {"uid": "1", "sec_uid": "s", "nickname": flag,
                              "follower_count": 5}},
    "aweme_search": {"aweme_list": [{"aweme_info": {"aweme_id": "a2", "desc": flag,
                                                    "author": author}}], "has_more": 0},
}[project]
snapshot = {"status": 200, "content_type": "application/json", "headers": {},
            "json": {"status_code": 0, **shape}}
open(args.json_out, "w", encoding="utf-8").write(json.dumps(snapshot))
'''

PROJECTS = ("aweme_detail", "comment_list", "comment_reply",
            "aweme_feed", "user_profile", "aweme_search")


# ------------------------------------------------------------------ normalize
def test_normalize():
    a = normalize.aweme(AWEME)
    assert a["aweme_id"] == AWEME["aweme_id"] and a["author"]["nickname"] == "傲安"
    assert a["statistics"]["digg_count"] == 23603 and a["duration"] == 60000
    assert a["is_image"] is False and normalize.aweme({}) is None

    c = normalize.comments([COMMENT])[0]
    assert c["cid"] == "7673750309165007665" and c["reply_comment_total"] == 2
    assert c["author"]["sec_uid"] == "MS4wU2"

    u = normalize.user(USER)
    assert u["nickname"] == "傲安" and u["follower_count"] == 1774701
    assert u["avatar"] == "https://x/a.jpeg" and normalize.user({}) is None

    items = normalize.aweme_list([{"aweme_info": AWEME}, {"nope": 1}])
    assert len(items) == 1 and items[0]["aweme_id"] == AWEME["aweme_id"]
    print("test_normalize OK")


def test_envelope():
    ok = DouyinCrawler._envelope({"json": {"status_code": 0, "x": 1}}, {"v": 1})
    assert ok == {"success": True, "status_code": 0, "message": None, "data": {"v": 1}}

    bad = DouyinCrawler._envelope({"json": {"status_code": 2483, "status_msg": "请先登录"}}, None)
    assert bad["success"] is False and bad["status_code"] == 2483 and bad["data"] is None
    assert "请先登录" in bad["message"]

    blocked = DouyinCrawler._envelope(
        {"content_type": "text/plain; charset=utf-8", "text": ""}, None)
    assert blocked["success"] is False and blocked["status_code"] is None
    assert "反爬" in blocked["message"] and blocked["data"] is None
    print("test_envelope OK")


def test_data_cookie_missing():
    crawler = DouyinCrawler()
    try:
        crawler._data_cookie("19999999999")
    except DouyinError as exc:
        assert "请先在 App 登录" in str(exc)
    else:
        raise AssertionError("无会话时应报 DouyinError")
    print("test_data_cookie_missing OK")


# ------------------------------------------------------------------ 调度接线
def test_run_data_wiring():
    original = settings.SIGNING_DIR
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for name in PROJECTS:
            (tmp / name).mkdir()
            (tmp / name / "main.py").write_text(FAKE_MAIN, encoding="utf-8")
        settings.SIGNING_DIR = tmp
        get_cache().set_json(f"dy_login:{PHONE}", {"sessionid": "s", "ttwid": TTWID}, ttl=60)
        try:
            crawler = DouyinCrawler()

            detail = crawler._aweme_detail_sync(PHONE, "7626316866109066511")
            assert detail["success"] is True
            assert detail["data"]["aweme_id"] == "7626316866109066511"   # 参数透传
            assert detail["data"]["author"]["sec_uid"] == TTWID          # cookie 传到了子进程

            comments = crawler._comment_list_sync(PHONE, "7626316866109066511", 0, 20)
            assert comments["data"]["total"] == 1 and comments["data"]["cursor"] == 1
            assert comments["data"]["comments"][0]["author"]["sec_uid"] == TTWID

            replies = crawler._comment_reply_sync(PHONE, "a", "c", 0, 20)
            assert replies["success"] is True and replies["data"]["comments"][0]["cid"] == "c2"

            feed = crawler._aweme_feed_sync(PHONE, 10, 1)
            assert feed["data"]["has_more"] is True and feed["data"]["items"][0]["aweme_id"] == "a1"

            user = crawler._user_profile_sync(PHONE, "MS4wSEC")
            assert user["data"]["follower_count"] == 5 and user["data"]["nickname"].startswith("check_login=")

            search = crawler._aweme_search_sync(PHONE, "mc", 0, 20)
            assert search["data"]["items"][0]["aweme_id"] == "a2"

            # 6 个路由都带 --check-login（登录态判定）
            assert detail["data"]["desc"] == "check_login=True", detail["data"]["desc"]
            assert comments["data"]["comments"][0]["text"] == "check_login=True"

            # 异步包装也通（后端路由就走它）
            assert asyncio.run(crawler.aweme_detail(PHONE, "x"))["data"]["aweme_id"] == "x"

            assert not list(tmp.rglob("dy_*_ck_*.json"))  # cookie 临时文件已清理
        finally:
            settings.SIGNING_DIR = original
            get_cache().delete(f"dy_login:{PHONE}")
    print("test_run_data_wiring OK")


def test_need_login_maps_to_auth_error():
    """项目 `--check-login` 失败（退出码 3 + NEED_LOGIN）→ DouyinAuthError（路由层 401）。"""
    need_login = ("import sys\n"
                  "sys.stderr.write('NEED_LOGIN: 会话不是有效的 www 登录态（status_code=8），请重新登录\\n')\n"
                  "sys.exit(3)\n")
    original = settings.SIGNING_DIR
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "aweme_detail").mkdir()
        (tmp / "aweme_detail" / "main.py").write_text(need_login, encoding="utf-8")
        settings.SIGNING_DIR = tmp
        get_cache().set_json(f"dy_login:{PHONE}", {"ttwid": TTWID}, ttl=60)
        try:
            try:
                DouyinCrawler()._aweme_detail_sync(PHONE, "x")
            except DouyinAuthError as exc:
                assert "请重新登录" in str(exc)
            else:
                raise AssertionError("NEED_LOGIN 应抬成 DouyinAuthError")
        finally:
            settings.SIGNING_DIR = original
            get_cache().delete(f"dy_login:{PHONE}")
    print("test_need_login_maps_to_auth_error OK")


def test_missing_cookie_is_400ish():
    """没有会话时 6 个接口都应抛 DouyinError（路由层映射成 400）。"""
    crawler = DouyinCrawler()
    for call in (
        lambda: crawler._aweme_detail_sync("19999999999", "a"),
        lambda: crawler._comment_list_sync("19999999999", "a", 0, 20),
        lambda: crawler._aweme_feed_sync("19999999999", 10, 1),
        lambda: crawler._user_profile_sync("19999999999", "s"),
        lambda: crawler._aweme_search_sync("19999999999", "k", 0, 20),
    ):
        try:
            call()
        except DouyinError:
            continue
        raise AssertionError("无会话时应报 DouyinError")
    print("test_missing_cookie_is_400ish OK")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("\n数据接口离线自检通过（未发任何网络请求）")
