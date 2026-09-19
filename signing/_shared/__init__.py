"""_shared —— 数据接口（`/aweme/v1/web/*`）**共用**的参数层（唯一一份）。

所有 `signing/<数据接口>/main.py` 都从这里取：

| 模块 | 内容 |
|---|---|
| `params` | 公共查询参数 `COMMON_PARAMS` + `build_params` / `build_url` |
| `signer` | a_bogus 生成（pyexecjs2 → `node/mod.js`） |
| `http` | cookie 载入 / 请求头 / 发起请求 / `--json-out` 落盘 |
| `logger` | 统一日志（stdout） |

**只为数据接口共用**：`node/mod.js` 只有一份（a_bogus 签名器），
不再每个接口复制一遍。登录类项目（send_code / sms_login）参数完全不同，不共用本包。

接口路径与业务参数仍在各项目自己的 `main.py` 里声明。
"""

from __future__ import annotations
