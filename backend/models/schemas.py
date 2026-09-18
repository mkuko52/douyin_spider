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
