"""data.py —— 数据接口（Phase 2）的 6 个明确路由。

每个路由对应 `signing/` 下一个独立项目，统一走 `core/crawler.py` 的 subprocess 调度：

| 路由 | 项目 | 抖音接口 |
|---|---|---|
| `POST /api/data/detail`   | `signing/aweme_detail`  | `/aweme/v1/web/aweme/detail/` |
| `POST /api/data/comments` | `signing/comment_list`  | `/aweme/v1/web/comment/list/` |
| `POST /api/data/replies`  | `signing/comment_reply` | `/aweme/v1/web/comment/list/reply/`（端点级反爬） |
| `POST /api/data/feed`     | `signing/aweme_feed`    | `/aweme/v1/web/tab/feed/` |
| `POST /api/data/user`     | `signing/user_profile`  | `/aweme/v1/web/user/profile/other/` |
| `POST /api/data/search`   | `signing/aweme_search`  | `/aweme/v1/web/search/item/`（需 www 登录态） |

手机号从 JWT（`phone` claim）取，后端用它在缓存里找 `dy_login:{phone}` / `dy_session:{phone}`
会话 cookie 传给签名项目（`--cookie-file`）。

每个路由都带 `--check-login`：项目先打 `/aweme/v1/web/notice/count/` 确认会话是
`www.douyin.com` 登录态，否则退出码 3 + `NEED_LOGIN` → 这里回 **401 请重新登录**
（而不是让 App 看到 `2483` / 空 body 去猜）。响应统一 `DataResponse`。
"""

from fastapi import APIRouter, Depends, HTTPException

from ..api.deps import current_phone
from ..core.crawler import DouyinAuthError, DouyinError, get_crawler
from ..models.schemas import (
    AwemeDetailRequest,
    AwemeFeedRequest,
    AwemeSearchRequest,
    CommentListRequest,
    CommentReplyRequest,
    DataResponse,
    UserProfileRequest,
)

router = APIRouter(prefix="/api/data", tags=["data"])


async def _safe(coro):
    """错误映射：会话不是 www 登录态 -> 401；参数/环境问题 -> 400；其余 500。"""
    try:
        return await coro
    except DouyinAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except DouyinError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - 统一兜底成 500
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/detail", response_model=DataResponse)
async def api_detail(req: AwemeDetailRequest, phone: str = Depends(current_phone)):
    """视频详情。`data` = 作品摘要（aweme_id / desc / author / statistics / duration）。"""
    return await _safe(get_crawler().aweme_detail(phone, req.aweme_id))


@router.post("/comments", response_model=DataResponse)
async def api_comments(req: CommentListRequest, phone: str = Depends(current_phone)):
    """评论列表。`data` = {total, has_more, cursor, comments:[…]}。"""
    return await _safe(get_crawler().comment_list(phone, req.aweme_id, req.cursor, req.count))


@router.post("/replies", response_model=DataResponse)
async def api_replies(req: CommentReplyRequest, phone: str = Depends(current_phone)):
    """评论回复。⚠️ 端点级反爬：抖音可能返回空 body（`success=false` + 说明）。"""
    return await _safe(get_crawler().comment_reply(
        phone, req.aweme_id, req.comment_id, req.cursor, req.count))


@router.post("/feed", response_model=DataResponse)
async def api_feed(req: AwemeFeedRequest, phone: str = Depends(current_phone)):
    """视频列表（推荐 tab feed）。`data` = {has_more, items:[…]}。"""
    return await _safe(get_crawler().aweme_feed(phone, req.count, req.refresh_index))


@router.post("/user", response_model=DataResponse)
async def api_user(req: UserProfileRequest, phone: str = Depends(current_phone)):
    """用户信息。`data` = {uid, sec_uid, nickname, unique_id, follower_count, …}。"""
    return await _safe(get_crawler().user_profile(phone, req.sec_user_id))


@router.post("/search", response_model=DataResponse)
async def api_search(req: AwemeSearchRequest, phone: str = Depends(current_phone)):
    """关键词搜索。⚠️ 需 `www.douyin.com` 登录态：未登录时 `status_code=2483`。"""
    return await _safe(get_crawler().aweme_search(
        phone, req.keyword, req.offset, req.count))
