"""normalize.py —— 抖音数据接口的原始响应 → 扁平记录。

抖音返回的 JSON 层级深、字段名不稳定（同一含义在不同接口/版本里可能不同名，
例如 `reply_comment_total` / `comment_reply_total`）。这里**集中还原一次**，
只保留后端/App 需要的字段，避免把 100KB+ 的原始 payload 原样丢给 App。

来源：旧项目 `douyin_spider/utils/client.py` 的 `restore_aweme` / `restore_comment`（已 live 验证）。
"""

from __future__ import annotations

from typing import Any, Mapping, Optional


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def author(user: Optional[Mapping[str, Any]]) -> dict:
    user = user or {}
    return {
        "uid": str(user.get("uid") or ""),
        "sec_uid": user.get("sec_uid") or "",
        "nickname": user.get("nickname") or "",
        "unique_id": user.get("unique_id") or "",
    }


def aweme(item: Optional[Mapping[str, Any]]) -> Optional[dict]:
    """作品摘要（详情 / 列表 / 搜索共用）。"""
    if not isinstance(item, Mapping) or not item.get("aweme_id"):
        return None
    statistics = item.get("statistics") or {}
    return {
        "aweme_id": str(item.get("aweme_id") or ""),
        "desc": item.get("desc") or "",
        "create_time": _int(item.get("create_time")),
        "aweme_type": _int(item.get("aweme_type")),
        "author": author(item.get("author")),
        "statistics": {
            "digg_count": _int(statistics.get("digg_count")),
            "comment_count": _int(statistics.get("comment_count")),
            "share_count": _int(statistics.get("share_count")),
            "collect_count": _int(statistics.get("collect_count")),
            "play_count": _int(statistics.get("play_count")),
        },
        "duration": _int((item.get("video") or {}).get("duration")),
        "is_image": bool(item.get("images")),
    }


def aweme_list(items: Any) -> list:
    """列表类响应（`aweme_list` / `data`），逐条 `aweme()` 后丢掉空项。"""
    out = []
    for item in items or []:
        if not isinstance(item, Mapping):
            continue
        # 搜索/聚合列表里作品可能包一层
        inner = item.get("aweme_info") or item.get("aweme_detail") or item
        record = aweme(inner)
        if record:
            out.append(record)
    return out


def comment(item: Optional[Mapping[str, Any]]) -> Optional[dict]:
    if not isinstance(item, Mapping) or not item.get("cid"):
        return None
    return {
        "cid": str(item.get("cid") or ""),
        "text": item.get("text") or "",
        "create_time": _int(item.get("create_time")),
        "digg_count": _int(item.get("digg_count")),
        "status": _int(item.get("status")),
        "ip_label": item.get("ip_label") or "",
        "reply_comment_total": _int(
            item.get("reply_comment_total") or item.get("comment_reply_total")
        ),
        "reply_id": str(item.get("reply_id") or ""),
        "author": author(item.get("user") or item.get("author")),
    }


def comments(items: Any) -> list:
    return [c for c in (comment(item) for item in items or []) if c]


def user(item: Optional[Mapping[str, Any]]) -> Optional[dict]:
    """主页用户信息（`/user/profile/other/` 的 `user`）。"""
    if not isinstance(item, Mapping) or not (item.get("uid") or item.get("sec_uid")):
        return None
    avatar = (item.get("avatar_larger") or item.get("avatar_thumb") or {}).get("url_list") or []
    return {
        "uid": str(item.get("uid") or ""),
        "sec_uid": item.get("sec_uid") or "",
        "nickname": item.get("nickname") or "",
        "unique_id": item.get("unique_id") or item.get("short_id") or "",
        "signature": item.get("signature") or "",
        "follower_count": _int(item.get("follower_count")),
        "following_count": _int(item.get("following_count")),
        "total_favorited": _int(item.get("total_favorited")),
        "aweme_count": _int(item.get("aweme_count")),
        "avatar": avatar[0] if avatar else "",
    }
