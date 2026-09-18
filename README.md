# 抖音数据采集（Douyin Spider）

抖音 Web **短信验证码登录协议**的完整复现 + FastAPI 后端 + Android 前端。

不抓包、不用 App，纯 HTTP 复现登录链路：`send_code` 发码 → `sms_login` 登录 → 拿到
`sessionid` / `sid_guard` / `x_tt_token` 等真实登录态，再由后端缓存、下发给 App。

> ⚠️ 仅供学习与安全研究。请只用自己的号码调试，详见文末[免责声明](#免责声明)。

---

## 架构

```
Android App (纯 Java UI)
     │ HTTP + JSON
     ▼
FastAPI 后端            api/auth.py    路由 + JWT
                        core/crawler.py 调度（subprocess + 全局锁 + 内存缓存）
     │ subprocess 调 signing/*/main.py        ← 唯一 HTTP 出口
     ▼
signing/send_code      参数 → a_bogus（浏览器 bdms 现场签）→ /passport/web/send_code/
signing/sms_login      参数 → a_bogus（nv8 跑页面同款 bdms 字节码）→ /passport/web/sms_login/
     │
     ▼
抖音 login.douyin.com
```

**两个关键设计**

- **后端自己不发抖音请求**：参数、签名、发请求全在 `signing/` 两个独立项目里完成，
  后端只用 `subprocess + --json-out` 调度（比解析 stdout 稳，stdout 有截断）。
- **发码会话必须复用到登录**：`a_bogus` 绑会话，换一个会话（新 `ttwid` = 新设备身份）
  登录会被判 `7 访问太频繁`。后端会缓存发码那条会话给登录用。

---

## 仓库结构

```
douyin_spider/
├── backend/              FastAPI：路由 + JWT + 调度 + 登录态缓存（不发抖音请求）
│   ├── api/auth.py       POST /api/auth/send_code · /api/auth/sms_login
│   ├── core/crawler.py   ★ subprocess 调 signing，归一化响应、缓存发码会话/登录态
│   └── core/cache.py     内存缓存（接口同 Redis，重启即丢）
│
├── signing/              签名与请求（各自独立项目，不互相 import）
│   ├── send_code/        发码：浏览器 bdms 现场签 a_bogus；自带 venv + node
│   │   ├── main.py       ★ 交付入口（端到端）
│   │   ├── node/         signer_server.mjs（常驻参数服务）+ mod.js
│   │   ├── utils/        passport / dtrait / artifact_service / signer
│   │   ├── assets/       dtrait_core.js · RSA 公钥 · sm3 · abogus
│   │   └── 分析报告.md    参数逆向报告（定位 / 分类 / 阻塞点与结论）
│   │
│   └── sms_login/        登录：nv8 签 a_bogus，全程无浏览器
│       ├── main.py       ★ 交付入口（默认 --abogus-source nv8）
│       ├── node/         abogus_server.mjs · dtrait_server.mjs
│       ├── utils/        passport / nv8_signer / dtrait / dtrait_signer
│       └── 分析报告.md    登录已打通报告
│
└── android/              纯 Java UI 前端（自建 build.py，无需 Gradle）
    ├── build.py          构建脚本：aapt2 / d8 / zipalign / apksigner
    ├── app/src/main/java/com/douyin/spider/
    │   ├── MainActivity.java   主页 / 数据 / 存储 / 我的（发码 60s 倒计时、登录态两套视图）
    │   ├── Api.java            HTTP 客户端
    │   └── Ui.java             设计系统（尺寸走 Ui.dp()，配色在 res/values/colors.xml）
    └── PROJECT_GUIDE.md
```

各部分的详细文档：
[`backend/README.md`](backend/README.md)（启动/排错/接口契约）·
[`signing/send_code/README.md`](signing/send_code/README.md) ·
[`signing/sms_login/README.md`](signing/sms_login/README.md) ·
[`android/AGENTS.md`](android/AGENTS.md)（整体架构与踩坑记录）

---

## 快速开始

### 1. 后端

```bash
# 在仓库根执行（backend 是命名空间包，cd backend 会 ImportError）
pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

curl http://127.0.0.1:8000/health        # {"status":"ok"}
```

浏览器打开 `http://127.0.0.1:8000/docs` 可直接填表调用。

### 2. 签名项目

两个项目共用 `signing/*/config.local.json`（**未入库**，需自己建）：

```json
{ "mobile": "", "code": "", "cookie_file": "", "verify_tls": false }
```

```bash
# send_code：自带 venv + node —— 首次 bootstrap（用系统 python 建 venv + 装依赖）
cd signing/send_code
python runtime/bootstrap.py --install
runtime/venv/Scripts/python.exe main.py --dry-run      # 只组参数不发请求
runtime/venv/Scripts/python.exe main.py                # 端到端（默认 auto：自动拉起常驻服务）

# sms_login：用当前解释器，全程无浏览器
cd signing/sms_login
pip install -r requirements.txt
python main.py --dry-run
python tests/test_vectors.py                           # 10 项离线固定向量
```

> `send_code` 需要 playwright 的 chromium 首次自动拉起（约 3~6s），之后每次约 1.6s。
> `sms_login` 每次冷启动 nv8 约 6s。

### 3. Android

```bash
cd android
python build.py --server-url http://192.168.1.100:8000   # 真机填局域网 IP
# 模拟器不用传：默认 http://10.0.2.2:8000
adb install -r douyin-spider.apk
```

### 4. 自检（离线，不发网络）

```bash
python backend/tests/test_crawler_offline.py
cd signing/send_code && runtime/venv/Scripts/python.exe tests/test_vectors.py
cd signing/sms_login && python tests/test_vectors.py
```

---

## 接口

| 方法 | 路径 | 请求体 |
|------|------|--------|
| POST | `/api/auth/send_code` | `{"phone":"13800138000"}` |
| POST | `/api/auth/sms_login` | `{"phone":"13800138000","code":"123456"}` |
| GET | `/health` `/docs` `/openapi.json` | — |

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

**注意：业务失败也是 HTTP 200**，调用方必须读 `success` 字段。

| `error_code` | 含义 |
|---|---|
| — | 成功 |
| `1203` | 验证码错误 / 过期 |
| `2156` | 系统繁忙（端点级风控） |
| `7` | 访问太频繁（**会话或设备级风控，不是参数错误**） |

`400` 才是参数/环境问题（手机号格式、验证码为空、签名项目跑不起来），此时**不会发起抖音请求**。

---

## 技术要点

| 环节 | 做法 |
|------|------|
| `enc` / `sign` / `qs` / `aid-sign` | 纯 Python 复现，与抓包逐位一致（`utils/passport.py`） |
| `x-tt-session-dtrait` | RSA-2048 包 `key‖iv` + AES-128-CBC（`utils/dtrait.py`） |
| `a_bogus`（发码） | 浏览器页面 `bdms` 现场签（XHR 被拦，不发业务请求） |
| `a_bogus`（登录） | **nv8 里跑页面同款 bdms 字节码**，无浏览器 |
| 后端 ↔ 签名 | `subprocess + --json-out` 落 JSON（比解析 stdout 稳） |
| 阻塞调用 | `asyncio.to_thread`（CLI 是同步的，不能卡事件循环） |
| 并发 | 全局 `asyncio.Lock`（工件服务只有一条浏览器会话） |

---

## 开发路线

**Phase 1 · 登录模块（当前）**
- [x] Android 纯 UI 前端
- [x] FastAPI 后端骨架
- [x] 逆向 `send_code` 签名算法
- [x] 逆向 `sms_login` 签名算法（nv8 路径无浏览器登录成功）
- [x] 后端对接两个签名项目
- [ ] Redis 真实接入（`cache.py` 现为内存 dict，重启即丢登录态）
- [ ] App ↔ 后端登录态联调

**Phase 2 · 核心爬虫** — 视频列表 / 视频详情 / 用户信息 / 评论

**Phase 3 · 数据处理** — 清洗 / 存储（MySQL·MongoDB）/ 导出

---

## 免责声明

本项目仅用于**个人学习、协议分析与安全研究**。

- `send_code` 会给目标号码**发送真实短信**并消耗风控额度，`sms_login` 会消耗验证码，
  请**只对自己的号码**使用，不要用于扫描他人号码。
- `signing/*/assets/` 中的 `webmssdk`、`bdms` 等 JS 版权归字节跳动所有，仅作逆向分析留存，
  请勿再分发或商用。
- 禁止用于批量注册、账号交易、爬取他人隐私数据或任何违反
  [抖音用户协议](https://www.douyin.com/agreements/) 与当地法律法规的用途。
- 使用本项目产生的一切后果由使用者自行承担。
