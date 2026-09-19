from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from datetime import datetime, timedelta
from ..config import settings

security = HTTPBearer()


def create_token(user_id: str, phone: str | None = None) -> str:
    """创建 JWT Token。

    `user_id`   = 抖音用户 id（App 展示用），向后兼容既有 token 格式。
    `phone`     = 手机号；数据接口要用它去缓存里取 `dy_login:{phone}` 会话，
                  所以新登录都会带上（user_id 可能是抖音 uid，不能当缓存键）。
    """
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    }
    if phone:
        payload['phone'] = phone
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """验证 JWT Token，返回 payload（含 `user_id` / 可选 `phone`）。"""
    try:
        return jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def current_phone(payload: dict = Depends(verify_token)) -> str:
    """数据接口依赖：从 token 取手机号（拿它去查后端缓存的登录态 cookie）。"""
    phone = payload.get("phone")
    if not phone:
        raise HTTPException(status_code=401, detail="token 缺少 phone，请重新登录")
    return phone
