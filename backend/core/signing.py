import execjs
import subprocess
import json
import re
from pathlib import Path
from typing import Optional


class SigningBridge:
    """签名桥接：根据接口自动选择 execjs 或 subprocess"""
    
    def __init__(self, signing_dir: str):
        self.signing_dir = Path(signing_dir)
        self._sync_contexts = {}
    
    def _is_async_js(self, endpoint: str) -> bool:
        """检测 JS 是否为异步代码"""
        entry_file = self.signing_dir / endpoint / 'entry.mjs'
        if not entry_file.exists():
            entry_file = self.signing_dir / endpoint / 'entry.js'
        
        code = entry_file.read_text(encoding='utf-8')
        return bool(re.search(r'\bawait\b|\basync\b', code))
    
    def _load_entry_module(self, endpoint: str) -> Path:
        """加载入口文件"""
        for name in ['entry.mjs', 'entry.js']:
            path = self.signing_dir / endpoint / name
            if path.exists():
                return path
        raise FileNotFoundError(f"Entry file not found for endpoint: {endpoint}")
    
    def _sign_sync(self, endpoint: str, params: dict) -> dict:
        """同步签名：execjs"""
        if endpoint not in self._sync_contexts:
            entry_file = self._load_entry_module(endpoint)
            code = entry_file.read_text(encoding='utf-8')
            self._sync_contexts[endpoint] = execjs.compile(code)
        
        ctx = self._sync_contexts[endpoint]
        return ctx.call('sign', json.dumps(params))
    
    def _sign_async(self, endpoint: str, params: dict) -> dict:
        """异步签名：subprocess + node"""
        entry_file = self._load_entry_module(endpoint)
        
        result = subprocess.run(
            ['node', str(entry_file)],
            input=json.dumps(params),
            capture_output=True,
            text=True,
            timeout=30,
            encoding='utf-8'
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"Signing failed: {result.stderr}")
        
        return json.loads(result.stdout)
    
    def sign(self, endpoint: str, params: dict) -> dict:
        """签名入口：自动路由到 sync/async"""
        if self._is_async_js(endpoint):
            return self._sign_async(endpoint, params)
        else:
            return self._sign_sync(endpoint, params)
    
    def verify_vector(self, endpoint: str, test_vector: dict) -> bool:
        """验证离线向量"""
        try:
            result = self.sign(endpoint, test_vector['input'])
            return result == test_vector['expected']
        except Exception:
            return False


# 全局实例
_signing_bridge: Optional[SigningBridge] = None


def get_signing_bridge() -> SigningBridge:
    global _signing_bridge
    if _signing_bridge is None:
        from ..config import settings
        _signing_bridge = SigningBridge(str(settings.SIGNING_DIR))
    return _signing_bridge
