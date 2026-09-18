from pathlib import Path
import os


class Settings:
    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    
    # JWT
    JWT_SECRET: str = os.getenv("JWT_SECRET", "douyin-spider-secret-key-change-in-production")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Signing
    SIGNING_DIR: Path = Path(__file__).parent.parent / "signing"
    SIGNING_PYTHON: str = ""  # 空 = 自动：签名项目自带 venv > 当前解释器
    ARTIFACT_SERVICE_URL: str = "http://127.0.0.1:8787"  # send_code 常驻工件服务
    SEND_CODE_TIMEOUT: int = 180
    SMS_LOGIN_TIMEOUT: int = 180
    SMS_LOGIN_ABOGUS_SOURCE: str = "nv8"  # nv8 = 无浏览器，实测登录成功
    SESSION_TTL_SECONDS: int = 1800  # 发码会话 / 登录态的缓存时长
    
    # Douyin
    DOUYIN_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.douyin.com/",
        "Origin": "https://www.douyin.com",
    }


settings = Settings()
