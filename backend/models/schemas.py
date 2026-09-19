from pydantic import BaseModel
from typing import Optional


class SendCodeRequest(BaseModel):
    """App → 后端：只需要手机号一个参数。"""

    phone: str


class SendCodeResponse(BaseModel):
    success: bool
    message: str
    error_code: Optional[int] = None  # 2156=风控拦截
    captcha: Optional[str] = None  # 风控要求过滑块时的 captcha 参数
    retry_after: Optional[int] = None  # 距下次可重发的秒数（服务端 retry_time）


class SmsLoginRequest(BaseModel):
    """App → 后端：手机号 + 验证码两个参数。"""

    phone: str
    code: str


class SmsLoginResponse(BaseModel):
    success: bool
    message: str
    error_code: Optional[int] = None  # 1203=码错误/过期；7/2156=风控拦截
    token: Optional[str] = None  # 后端 JWT，App 用它访问后续接口
    user_id: Optional[str] = None
    session_id: Optional[str] = None  # 抖音 sessionid
    cookies: Optional[dict] = None  # 抖音登录态 cookie（sessionid/sid_guard/...）


# ---------------------------------------------------------------- 数据接口（Phase 2）
# 手机号从 JWT（`phone` claim）取，不再在 body 里传。

class AwemeDetailRequest(BaseModel):
    """视频详情：作品 id。"""
    aweme_id: str


class CommentListRequest(BaseModel):
    """评论列表：作品 id + 翻页。"""
    aweme_id: str
    cursor: int = 0
    count: int = 20


class CommentReplyRequest(BaseModel):
    """评论回复：作品 id + 父评论 cid + 翻页。"""
    aweme_id: str
    comment_id: str
    cursor: int = 0
    count: int = 20


class AwemeFeedRequest(BaseModel):
    """视频列表（推荐 tab feed）。"""
    count: int = 10
    refresh_index: int = 1


class UserProfileRequest(BaseModel):
    """用户信息：主页 sec_uid（从视频/评论的 author.sec_uid 取）。"""
    sec_user_id: str


class AwemeSearchRequest(BaseModel):
    """关键词搜索（需 www.douyin.com 登录态）。"""
    keyword: str
    offset: int = 0
    count: int = 20


class DataResponse(BaseModel):
    """6 个数据接口统一响应。`data` 的形状随接口而定（见各路由）。"""
    success: bool
    status_code: Optional[int] = None  # 拖音业务状态码（0=成功）
    message: Optional[str] = None  # 失败原因（2483 未登录 / 空 body 被反爬 等）
    data: Optional[dict] = None
