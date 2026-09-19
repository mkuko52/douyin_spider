from fastapi import APIRouter, HTTPException
from ..models.schemas import (
    SendCodeRequest, SendCodeResponse,
    SmsLoginRequest, SmsLoginResponse
)
from ..core.crawler import get_crawler, DouyinError
from ..api.deps import create_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/send_code", response_model=SendCodeResponse)
async def api_send_code(req: SendCodeRequest):
    """发送验证码（会给该号码发真实短信）"""
    try:
        result = await get_crawler().send_code(req.phone)
    except DouyinError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return SendCodeResponse(
        success=result['success'],
        message=result['message'],
        error_code=result['error_code'],
        captcha=result['captcha'],
        retry_after=result['retry_after'],
    )


@router.post("/sms_login", response_model=SmsLoginResponse)
async def api_sms_login(req: SmsLoginRequest):
    """短信登录；成功后返回后端 JWT + 抖音登录态 cookie"""
    try:
        result = await get_crawler().sms_login(req.phone, req.code)
    except DouyinError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not result['success']:
        return SmsLoginResponse(
            success=False,
            message=result['message'],
            error_code=result['error_code'],
        )

    user_id = result['user_id'] or req.phone
    return SmsLoginResponse(
        success=True,
        message=result['message'],
        error_code=result['error_code'],
        token=create_token(user_id, phone=req.phone),
        user_id=user_id,
        session_id=result['session_id'],
        cookies=result['cookies'],
    )
