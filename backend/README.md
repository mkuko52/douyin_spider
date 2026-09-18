# backend —— 启动与运维

纯调度后端：**自己不发抖音请求**，把发码/登录整条请求委托给 `signing/{send_code,sms_login}`，
只负责「路由 + JWT + 发码会话与登录态的缓存」。

架构、目录结构、踩坑记录见 [`../android/AGENTS.md`](../android/AGENTS.md)。

---

## 1. 一次性准备

```bash
cd D:\spider_projects\web\douyin_spider
pip install -r backend\requirements.txt
```

## 2. 启动

**必须在仓库根 `douyin_spider\` 下执行**（`backend` 是命名空间包）：

```bash
cd D:\spider_projects\web\douyin_spider
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

开发时自动重载：

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

> ⚠️ **不要用 `cd backend && python main.py`** —— 相对 import 会直接报
> `ImportError: attempted relative import with no known parent package`。

### 确认起来了

```bash
curl http://127.0.0.1:8000/health      # {"status":"ok"}
```

浏览器打开 `http://127.0.0.1:8000/docs` 可直接填表调用（Swagger UI，自带前端）。

---

## 3. 依赖的运行环境（一般都已经就绪）

| 项 | 位置 / 要求 |
|---|---|
| `send_code` 的解释器 | `signing/send_code/runtime/venv`（自带，含 aiohttp / playwright / cryptography） |
| `sms_login` 的解释器 | 启动后端的同一个 Python（需 requests / pyexecjs2 / cryptography） |
| nv8 的 node | `signing/send_code/runtime/node_local/node.exe`（v22.20.0） |
| playwright 浏览器 | `%LOCALAPPDATA%\ms-playwright\chromium-*`（发码要用） |

`crawler._python()` 自动挑选：`SIGNING_PYTHON` 配置 > 项目自带 venv > 当前解释器。
要强制指定就在 `config.py` 里设 `SIGNING_PYTHON`。

---

## 4. 接口契约

| 方法 | 路径 | 请求体 |
|---|---|---|
| POST | `/api/auth/send_code` | `{"phone":"13800138000"}` |
| POST | `/api/auth/sms_login` | `{"phone":"13800138000","code":"123456"}` |
| GET | `/health` `/docs` `/redoc` `/openapi.json` | — |

```bash
# 发码（会给该号码发真实短信）
curl -X POST http://127.0.0.1:8000/api/auth/send_code \
     -H "Content-Type: application/json" -d '{"phone":"13800138000"}'
# -> {"success":true,"message":"success","error_code":null,"captcha":null,"retry_after":60}

# 登录
curl -X POST http://127.0.0.1:8000/api/auth/sms_login \
     -H "Content-Type: application/json" -d '{"phone":"13800138000","code":"123456"}'
# -> {"success":true,"message":"success","error_code":0,"token":"<后端JWT>",
#     "user_id":"...","session_id":"...","cookies":{"sessionid":"...","sid_guard":"..."}}
```

**状态码约定**

| 场景 | HTTP | body |
|---|---|---|
| 缺字段 | `422` | pydantic 的 detail |
| 参数/环境问题（手机号格式、验证码为空、签名项目跑不起来） | `400` | `{"detail":"..."}`，**不会发抖音请求** |
| 抖音侧业务失败 | `200` | `{"success":false,"message":"...","error_code":...}` |
| 成功 | `200` | `{"success":true,...}` |

> **业务失败也是 HTTP 200**，调用方必须读 `success` 字段，不能只看状态码。

`error_code` 含义：`2156` 系统繁忙（风控）/ `1203` 验证码错误或过期 / `7` 访问太频繁（会话或频率风控，非参数错误）。

---

## 5. 一次登录的完整链路

```
App  POST /api/auth/send_code {phone}
 └─ crawler 起子进程：send_code/main.py --mobile <phone> --service-url http://127.0.0.1:8787
     └─ 8787 常驻工件服务（浏览器页面 bdms 现场签 a_bogus + dtrait）→ 抖音 /passport/web/send_code/
 └─ 成功后再 GET http://127.0.0.1:8787/cookies  ← 拿「发码那条会话」
 └─ 缓存 dy_session:{phone}（TTL 30min）

App  POST /api/auth/sms_login {phone, code}
 └─ crawler 把 dy_session 写成临时 cookie 文件
 └─ 起子进程：sms_login/main.py --mobile --code --cookie-file ... --save-cookies ... --abogus-source nv8
     └─ nv8 里跑页面同款 bdms 字节码签 a_bogus → 抖音 /passport/web/sms_login/
 └─ 成功：从 --save-cookies 的文件里取 sessionid/sid_guard/x_tt_token… → 缓存 dy_login:{phone}
 └─ 返回后端 JWT + 抖音 cookie

Phase 2 爬虫用 crawler.get_login_state(phone) 取登录态 cookie
```

**发码会话必须复用到登录**：换一个会话（新 `ttwid` = 新设备身份）登录会被判 `7 访问太频繁`。

---

## 6. 端口与出网

| 地址 | 说明 |
|---|---|
| `0.0.0.0:8000` | 本服务，给 App / 浏览器访问 |
| `127.0.0.1:8787` | `send_code` 常驻工件服务（**仅本机监听**）。首次发码自动拉起（~3s），也可手动预热：`cd signing\send_code && start_service.bat` |
| `login.douyin.com` · `www.douyin.com` · `ttwid.bytedance.com` | 由 signing 项目出网（443） |
| `*.bytegoofy.com` · 其它 `*.douyin.com` 静态域 | 发码时浏览器要加载页面 SDK（secsdk/bdms/webmssdk） |

- **不需要 Redis**：`core/cache.py` 现在是进程内内存字典（接口与 Redis 一致，后续可替换）。
- TLS：`signing/*/config.local.json` 里 `verify_tls: false`（不校验证书）。要严格校验就改成 `true`。

---

## 7. 排错

| 现象 | 原因 / 处理 |
|---|---|
| `ImportError: attempted relative import...` | 用了 `cd backend && python main.py`；改成在仓库根跑 `python -m uvicorn backend.main:app` |
| `send_code/main.py 不认识 --json-out（被改写/回退过）` | 签名项目的 `main.py` 被整体重写过。`--json-out` 是 `crawler` 的**必需参数**，补回去（见 AGENTS.md「签名模块结构」） |
| 登录返回 `7 访问太频繁` | 发码会话没复用上（看日志有没有「未取到发码会话」警告），或号码短时间内调太密 |
| 发码返回 `2156 系统繁忙` | 端点级风控。`127.0.0.1:8787` 工件服务没起来 / 或用了 nv8 自产的 a_bogus（该端点拒收）→ 必须走 service/browser 形态（`crawler` 用 `main.py` 默认的 `--abogus-source auto`） |
| 第一次调 `/send_code` 很慢（3~5s） | 正常：在拉起 8787 工件服务 + 开浏览器。之后每次约 1.6s |
| `sms_login` 要 ~6s | 正常：每次都要冷启动 nv8（约 4.5s）。想更快就得给 `sms_login` 也做常驻工件服务（见 AGENTS.md「登录态流转」） |
| 登录态重启就没了 | `cache.py` 是内存实现。要持久化就换真 Redis |
| 多进程下登录互相看不到 | **不要加 `--workers`**：内存缓存 + 进程内 `asyncio.Lock` 都只在单进程内有效 |

**日志**：uvicorn 输出到 stdout；`crawler` 的告警走标准 `logging`（如「未取到发码会话…」）。

---

## 8. App 侧连接地址

| 场景 | 填什么 |
|---|---|
| Android 模拟器 | `http://10.0.2.2:8000`（`ServerDefault.URL` 默认值，10.0.2.2 = 宿主机） |
| 真机 | `http://<本机局域网IP>:8000`（`ipconfig` 查 IPv4），构建时 `python android/build.py --server-url http://192.168.x.x:8000` |
| 浏览器 / 本机脚本 | `http://127.0.0.1:8000` |

---

## 9. 自检

```bash
# 离线自检：响应契约 + CLI 接线，不发任何网络请求
python backend/tests/test_crawler_offline.py
```

## 10. 合规提醒

`/api/auth/send_code` 会给目标号码**发真实短信**并消耗风控额度，`/api/auth/sms_login` 会消耗验证码。
只对自己的号码使用，别拿去扫别人的号；连续测试会把风控推高。
