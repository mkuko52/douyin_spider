import json
import time
from typing import Optional
from ..config import settings


class RedisCache:
    """Redis 缓存（简化版，可替换为实际 Redis 客户端）"""
    
    def __init__(self):
        self._store = {}  # 简单内存存储，生产环境用 redis-py
    
    def set(self, key: str, value: str, ttl: int = 300):
        """设置缓存"""
        self._store[key] = {
            'value': value,
            'expire_at': time.time() + ttl
        }
    
    def get(self, key: str) -> Optional[str]:
        """获取缓存"""
        item = self._store.get(key)
        if item and item['expire_at'] > time.time():
            return item['value']
        return None
    
    def delete(self, key: str):
        """删除缓存"""
        self._store.pop(key, None)

    # dict 便捷读写（会话 cookie 这类结构化值）
    def set_json(self, key: str, value: dict, ttl: int = 300):
        self.set(key, json.dumps(value, ensure_ascii=False), ttl)

    def get_json(self, key: str) -> dict:
        raw = self.get(key)
        return json.loads(raw) if raw else {}


# 全局实例
_cache: Optional[RedisCache] = None


def get_cache() -> RedisCache:
    global _cache
    if _cache is None:
        _cache = RedisCache()
    return _cache
