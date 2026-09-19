# AGENTS.md — 项目整体架构与经验教训

## 项目架构

### 整体架构

```
Android App (纯 UI 前端)
     ↓ HTTP(JSON)  POST /api/auth/send_code, /api/auth/sms_login
FastAPI Backend  api/auth.py（登录）· api/data.py（数据 6 路由）  路由 + JWT
     ↓           core/crawler.py 调度（asyncio.to_thread；登录环节加全局锁）
     ↓ subprocess 调 signing/<项目>/main.py   ← 唯一 HTTP 出口
抖音 login.douyin.com  /passport/web/send_code/ · /passport/web/sms_login/
     ↑
core/cache.py   dy_session:{phone}（发码会话）→ dy_login:{phone}（登录态）
     ↓
JWT + 抖音登录态 cookie 返回 App
```

发码所需的 `a_bogus` / `dtrait` 由 `send_code` 的常驻工件服务（`127.0.0.1:8787`，浏览器+Node
只启一次）现场生成；登录走 `sms_login` 的 nv8 路径（无浏览器）。

> Phase 2 数据接口（`signing/aweme_detail` 等 6 个 + 共用的 `signing/_shared`）见下文
> 「签名模块结构」。它们**尚未接入 backend**，所以上图只画已接线的登录链路。

### 技术栈

| 层级 | 技术 | 职责 |
|------|------|------|
| Android | 纯 Java UI | 界面交互，调用后端 API |
| Backend | FastAPI (Python) | API 路由、JWT、调度、登录态缓存 |
| HTTP 出口 | send_code: aiohttp / sms_login: requests；数据接口共用 `_shared`（requests） | **由 signing 项目独占**，backend 不发抖音请求 |
| 参数与签名 | sign/qs/aid-sign/enc 纯 Python；a_bogus→浏览器 bdms / nv8 / `_shared` 的 mod.js；dtrait→nv8+RSA/AES | 见各项目 `分析报告.md` / README |
| 后端↔签名 | subprocess + `--json-out` | 登录类项目各自独立（venv + 同名 `utils`）；数据接口共用 `signing/_shared` |
| 缓存 | 内存 dict（`cache.py`，接口同 Redis） | 发码会话、登录态 |

### 目录结构

#### 后端项目结构

```
backend/                              # FastAPI 后端（只做调度与登录态，不发抖音请求）
├── main.py                           # 入口：FastAPI app、CORS、路由注册
├── config.py                         # 配置：Redis/JWT/Signing 路径/超时/工件服务地址
├── requirements.txt                  # fastapi uvicorn pyjwt pydantic（web）+ aiohttp requests cryptography pyexecjs2（签名项目用）
├── start.bat / start.sh              # ★用后端自带 venv 起服务
├── runtime/
│   ├── bootstrap.py                  # 建/检后端自带 venv（--install / --check）
│   └── venv/                         # 后端自带 venv（gitignored，可重建）
│                                     #   同时当「没有自带 venv 的签名项目」的解释器
│
├── api/                              # 路由层
│   ├── __init__.py
│   ├── auth.py                       # POST /api/auth/send_code   {phone}
│   │                                 # POST /api/auth/sms_login   {phone, code}
│   ├── data.py                       # ★数据接口 6 个明确路由（Phase 2）
│   │                                 # POST /api/data/detail    {aweme_id}
│   │                                 # POST /api/data/comments  {aweme_id, cursor, count}
│   │                                 # POST /api/data/replies   {aweme_id, comment_id, cursor, count}
│   │                                 # POST /api/data/feed      {count, refresh_index}
│   │                                 # POST /api/data/user      {sec_user_id}
│   │                                 # POST /api/data/search    {keyword, offset, count}
│   └── deps.py                       # create_token(user_id, phone) / verify_token / current_phone（JWT）
│
├── core/                             # 核心层
│   ├── __init__.py
│   ├── crawler.py                    # ★调度层：subprocess 调 signing 的各 main.py，
│   │                                 #   归一化响应、缓存「发码会话 / 登录态」
│   ├── normalize.py                  # ★拖音原始响应 → 扁平记录（aweme / comment / user / aweme_list）
│   ├── cache.py                      # 缓存（内存实现，set/get/set_json/get_json，接口同 Redis）
│   └── signing.py                    # ⚠️ 早期 execjs 桥接脚手架，当前无调用方（见「调度策略」）
│
├── models/                           # 数据模型
│   ├── __init__.py
│   └── schemas.py                    # Pydantic：SendCode/SmsLogin + 6 个数据接口的请求与 DataResponse
│
└── tests/
    ├── test_crawler_offline.py       # 离线自检（登录响应契约 + CLI 接线，不发网络）
    └── test_data_offline.py          # 离线自检（数据接口：normalize + _envelope + 6 项目调度接线）
```

#### 签名模块结构

> 每个接口各自是一个独立 project-root（send_code/sms_login 是登录类，其余是数据类；
> 彼此不 import，同名 `utils` 包不共享）。
> **本节结构必须与磁盘实际目录逐行一致**（改完代码/新增文件后同步更新这里），
> 以 `find signing/send_code signing/sms_login -maxdepth 2` 为准。

```
signing/
├── send_code/                        # 发码：POST https://login.douyin.com/passport/web/send_code/
│   ├── main.py                       # ★交付入口（端到端：组参数 → 签名 → 发请求 → 打印响应）
│   ├── README.md                     # 交付文档
│   ├── 分析报告.md                   # 参数逆向报告（逆向定位 / 参数分类 / 阻塞点与结论）
│   ├── config.local.json             # mobile / cookie_file / verify_tls
│   ├── requirements.txt              # cryptography requests aiohttp playwright
│   ├── .gitignore
│   ├── start_service.bat             # 常驻工件服务启动（Windows）
│   ├── start_service.sh              # 常驻工件服务启动（Linux/macOS）
│   ├── node/
│   │   ├── signer_server.mjs         # 常驻参数服务：dtrait 现场采集 + a_bogus（JSON-Lines over stdio）
│   │   └── mod.js                    # 还原的 a_bogus 签名器（SM3 + 环境桩）
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── passport.py               # enc / sign / qs / aid-sign / 公共参数（纯 Python）
│   │   ├── dtrait.py                 # x-tt-session-dtrait：RSA-2048 包 key‖iv + AES-128-CBC
│   │   ├── signer.py                 # Python → Node 桥（常驻子进程）
│   │   ├── artifact_service.py       # ★常驻窄工件服务：GET /health /cookies，POST /abogus /dtrait
│   │   ├── browser_abogus.py         # playwright 形态：页面 bdms 现场签 a_bogus（XHR 被拦，不发业务请求）
│   │   ├── ticketguard.py            # bd_ticket_guard 相关
│   │   └── logger.py
│   ├── assets/                       # 逆向工件（dtrait 核心 / RSA 公钥 / sm3 / webmssdk）
│   │   ├── dtrait_core.js
│   │   ├── dtrait_rsa.json
│   │   ├── dtrait_payload.json
│   │   ├── sm3.js
│   │   ├── abogus.js
│   │   └── webmssdk.es5.1.0.0.20.js
│   ├── runtime/                      # 项目自带运行时（不读本机环境变量）
│   │   ├── bootstrap.py              # 安装 venv
│   │   ├── run.py                    # 等价于 python main.py（用自带 venv）
│   │   ├── venv/                     # 项目自带 venv（Include/ Lib/ Scripts/ pyvenv.cfg）
│   │   └── node_local/               # 项目自带 node（node.exe）
│   ├── tests/
│   │   └── test_vectors.py           # 9 项离线固定向量（不发网络）
│   ├── output/                       # 运行产物：last_request.json（本次构造的 url+body）、日志
│   ├── js_reverse_cache/             # 证据缓存（临时，可整目录丢弃）
│   │   ├── checkpoint.json / checkpoint.md
│   │   ├── recon/                    # 36 个侦察脚本（bdms/abogus/secsdk/dtrait 探针、diff、replay）
│   │   ├── source/                   # 27 个源码（bdms.js、sdk-glue.js、secsdk、client-entry、wasm…）
│   │   ├── env/                      # 17 份环境/结论笔记（send_code_root_cause_abogus.md 等）
│   │   ├── samples/                  # 15 份抓包样本/固定向量
│   │   └── private/                  # 8 份私有状态（browser_state.json、dtrait_payload_cache.json…）
│   └── （无 ast/ iv8/：这两个目录不存在）
│
└── sms_login/                        # 登录：POST https://login.douyin.com/passport/web/sms_login/
    ├── main.py                       # ★交付入口（默认 --abogus-source nv8，完全无浏览器）
    ├── README.md
    ├── 分析报告.md                   # 登录已打通报告（nv8 签 a_bogus，实测 message:success）
    ├── config.local.json             # mobile / code / cookie_file / verify_tls
    ├── requirements.txt              # requests pyexecjs2 cryptography（playwright 可选）
    ├── .gitignore
    ├── node/
    │   ├── abogus_server.mjs         # nv8 里跑页面同款 bdms 字节码 → a_bogus
    │   ├── dtrait_server.mjs         # nv8 采集 dtrait payload
    │   └── mod.js                    # 公开移植版 a_bogus（--abogus-source modjs，服务端不认）
    ├── utils/
    │   ├── __init__.py
    │   ├── passport.py               # enc / sign / qs / aid-sign / common_params / body_sms_login
    │   ├── nv8_signer.py             # Python → Node(nv8) 桥：bdms 字节码签 a_bogus（常驻 node 子进程）
    │   ├── dtrait_signer.py          # nv8 采集 dtrait payload（本地，默认）
    │   ├── dtrait.py                 # RSA + AES 拼 x-tt-session-dtrait 头
    │   ├── signer.py                 # pyexecjs2 桥（mod.js）
    │   ├── browser_artifacts.py      # playwright 形态（--abogus-source browser）
    │   └── logger.py
    ├── assets/
    │   ├── dtrait_core.js
    │   ├── dtrait_rsa.json
    │   ├── dtrait_payload.json
    │   └── webmssdk.es5.1.0.0.20.js
    ├── tests/
    │   ├── test_vectors.py           # 10 项离线固定向量
    │   └── e2e_login.py              # ⚠️ 测试脚本（send_code→登录的接线验证），后端不得依赖
    ├── output/
    │   └── last_request.json
    ├── js_reverse_cache/
    │   ├── checkpoint.json / checkpoint.md
    │   ├── recon/                    # 7 个诊断脚本（a_bogus A/B、cookie 子集扫描、隔离实验）
    │   ├── source/                   # 3 个源码（bdms.js、sdk-glue.js、secsdk-runtime34.js）
    │   ├── env/                      # 6 份结论 JSON（isolate_sms_login_result.json 等）
    │   ├── samples/                  # 1 份浏览器固定向量 sms_login_browser_vector.json
    │   └── private/                  # 10 份会话/指纹状态（*_session.json、browser_state.json…）
    └── （无 runtime/：直接用当前解释器；需要 execjs/requests/cryptography）
```

**数据接口（Phase 2，每个接口一个独立 project-root）**：每个项目只有 `main.py`（接口路径 +
业务参数 + 打印摘要）；**公共参数 / a_bogus / cookie / 请求 / `--json-out` 全部共用
`signing/_shared/`（唯一一份）**，不在各接口重复复制。数据接口（`/aweme/v1/web/*`）
**只需 `a_bogus`，不需要浏览器 / dtrait**。

```
signing/
├── _shared/                          # ★ 数据接口共用（唯一一份）
│   ├── params.py                     # 公共参数 COMMON_PARAMS + build_params / build_url
│   ├── node.py                       # ★项目自带 node 的解析（DOUYIN_NODE → send_code/runtime/node_local → PATH）
│   ├── signer.py                     # pyexecjs2 → node/mod.js（sign_url / a_bogus）
│   ├── nv8.py                        # 真 bdms a_bogus（replies 必须用；复用 sms_login/node/abogus_server.mjs）
│   ├── nv8_service.py                # ★常驻 nv8 工件服务（HTTP :8789，Node/bdms 只启一次）
│   ├── start_nv8_service.bat / .sh   # 启常驻服务
│   ├── http.py                       # load_cookie_file / build_headers / sign / request / write_json_out
│   │                                 # + 登录态检查：PATH_LOGIN_CHECK / is_logged_in / assert_login
│   ├── cli.py                        # 通用开关（--cookie-file/--dry-run/--verbose/--verify-tls/--check-login/--config/--json-out）
│   ├── logger.py
│   ├── node/mod.js                   # a_bogus 签名器（与 send_code/sms_login 字节一致）
│   └── tests/test_vectors.py         # 6 条 a_bogus 冻结向量 + build_url/sign_url + 登录判定
│
├── aweme_detail/                     # 视频详情  GET /aweme/v1/web/aweme/detail/
├── comment_list/                     # 评论列表  GET /aweme/v1/web/comment/list/
├── comment_reply/                    # 评论回复  GET /aweme/v1/web/comment/list/reply/（需真 bdms a_bogus）
├── aweme_feed/                       # 视频列表  GET /aweme/v1/web/tab/feed/
├── user_profile/                     # 用户信息  GET /aweme/v1/web/user/profile/other/
└── aweme_search/                     # 关键词搜索 GET /aweme/v1/web/search/item/（需 www 登录态）
    ├── main.py                       # ★只有「接口路径 + 业务参数 + 打印摘要」
    ├── README.md
    ├── config.local.json             # cookie_file / verify_tls（gitignored）
    ├── requirements.txt              # requests + pyexecjs2
    ├── tests/test_vectors.py         # 本接口 URL/参数组装（1 项；a_bogus 向量在 _shared）
    └── output/last_request.json
```

> 数据接口的 `--json-out` 契约：`{path, status, content_type, headers, json}`
> （非 JSON 响应时给 `text`）。

两个项目都支持 `--json-out <file>`：把响应（status / content_type / 风控响应头 / 解析后的 JSON）
写成 JSON 文件——backend 读它，**不解析 stdout**（stdout 有 4000 字截断 + 中文日志）。

> ⚠️ **`--json-out` 是后端调用的必需参数**：`crawler._run_cli` 每次都传它。
> 如果重写/回退 `main.py` 时把它删了，后端会直接报
> `不认识 --json-out（被改写/回退过）` —— 改完记得补回。


#### Android 前端结构

```
android/                              # 纯 UI 前端
├── app/src/main/java/com/douyin/spider/
│   ├── MainActivity.java             # 主界面：登录表单、状态管理、发码 60s 倒计时
│   │                                 #   doLogin() → POST /api/auth/sms_login
│   │                                 #   sendVerificationCode() → POST /api/auth/send_code
│   ├── Api.java                      # HTTP 客户端：postJsonAsync / jsonBool / jsonValue / jsonNumber
│   ├── Ui.java                       # UI 样式：圆角、颜色、间距
│   ├── Icons.java                    # 图标绘制：手机号、验证码、箭头
│   └── ServerDefault.java            # 服务器地址配置（模拟器 10.0.2.2:8000；真机用局域网 IP）
├── build.py                          # 构建脚本：aapt2/d8/zipalign/apksigner（无需 Gradle）
└── douyin-spider.apk                 # 产物（python build.py 生成）
```

## 核心设计决策

### 调度策略（真实形态：backend 不发抖音请求）

```python
# core/crawler.py —— 参数/签名/发请求全在 signing 项目里，backend 只调度
async def send_code(self, phone):
    async with self._lock:                                   # 工件服务只有一条浏览器会话
        return await asyncio.to_thread(self._send_code_sync, phone)

def _run_cli(self, project, args, timeout):                 # 同步 CLI → 线程，不阻塞事件循环
    subprocess.run([python, f"signing/{project}/main.py", *args, "--json-out", tmp], ...)
```

| 环节 | 实现 | 原因 |
|------|------|------|
| 参数 / 签名 / 发请求 | signing 两个 `main.py` | 已验证交付物，**独占 HTTP 出口**；两块各有 venv + 同名 `utils` 包，不能 import |
| 后端 ↔ 签名 | subprocess + `--json-out` 落 JSON | 比解析 stdout 稳（stdout 有 4000 字截断 + 中文日志） |
| 阻塞调用 | `asyncio.to_thread` | CLI 是同步的，不能卡 FastAPI 事件循环 |
| 并发 | 全局 `asyncio.Lock` | 工件服务只持有一条浏览器会话，并发发码会共用设备身份撞风控 |
| 发码 → 登录 | 缓存 `dy_session:{phone}`，登录当 `--cookie-file` | `a_bogus` 绑会话，换会话登录被判 `7 访问太频繁` |

> `core/signing.py`（execjs/subprocess 自动路由）是早期脚手架：当时的假设是「backend 自己
> 组包、只把签名外包」。实际形态是「整条请求外包给 signing」，所以它目前**无调用方**。

### 登录态流转

```
send_code(phone)   → 抖音回 JSON（成功：message=success + retry_time）
                   → 顺手 GET 工件服务 127.0.0.1:8787/cookies（「发码那条会话」）
                   → 缓存 dy_session:{phone}                     （TTL 30min）
sms_login(phone,code) → 用 dy_session 当 --cookie-file + --save-cookies
                   → 成功：sessionid/sid_guard/x_tt_token… → 缓存 dy_login:{phone}
api/auth.py        → 返回 JWT(create_token) + cookies 给 App
Phase 2 爬虫       → crawler.get_login_state(phone) 取登录态 cookie
```

### 接口契约

前端（App）只需要传这几个参数，多一个都不用：

| 接口 | 方法 | 请求体 | 说明 |
|------|------|--------|------|
| `/api/auth/send_code` | POST | `{"phone": "13800138000"}` | **1 个参数**；会给该号码发**真实短信** |
| `/api/auth/sms_login` | POST | `{"phone": "13800138000", "code": "123456"}` | **2 个参数**；验证码由用户从短信里塡 |

```bash
curl -X POST http://127.0.0.1:8000/api/auth/send_code \
     -H "Content-Type: application/json" -d '{"phone":"13800138000"}'
# 成功 -> {"success":true,"message":"success","error_code":null,
#          "captcha":null,"retry_after":60}

curl -X POST http://127.0.0.1:8000/api/auth/sms_login \
     -H "Content-Type: application/json" \
     -d '{"phone":"13800138000","code":"123456"}'
# 成功 -> {"success":true,"message":"success","error_code":0,
#          "token":"<后端 JWT>","user_id":"13800138000",
#          "session_id":"<抖音 sessionid>","cookies":{"sessionid":"…","sid_guard":"…"}}
```

状态码：`422` = 缺字段（pydantic）；`400` = 参数/环境问题（手机号格式、验证码为空、签名项目跑不起来，**不会发抖音请求**）；
`200` + `success:false` = 抖音侧业务失败，看 `error_code`（不发 HTTP 错误码，App 直接拿 `message` 展示）。

**响应契约**（已按真实响应归一化，`tests/test_crawler_offline.py` 钉死）：

| 接口 | 成功 | 失败 |
|------|------|------|
| `send_code` | `message:"success"` + `data.retry_time/mobile_ticket` | `data.error_code=2156` 系统繁忙（风控） |
| `sms_login` | `message:"success"` 或 `data.error_code=0` + 会话 cookie | `1203` 码错/过期；`7`/`2156` 风控（**非参数问题**） |

> ⚠️ 抖音 `/passport/web/*` 的响应是 `{data:{error_code,description},message}`，**不是**
> `{status_code,description}`。按后者取字段会永远得到 `success=True` 且 token 为 `None`。

### 数据接口契约（Phase 2，6 个明确路由）

全部 `POST /api/data/*`，需 `Authorization: Bearer <后端 JWT>`（登录时拿到的 token）。
**手机号不在 body 里** —— 从 JWT 的 `phone` claim 取，后端用它去缓存找 `dy_login:{phone}` 会话。

| 路由 | 请求体 | `data` 形状 | 对应 signing 项目 |
|------|--------|-------------|------------------|
| `/api/data/detail` | `{"aweme_id":"<id>"}` | 作品摘要（aweme_id/desc/author/statistics/duration/is_image） | `aweme_detail` |
| `/api/data/comments` | `{"aweme_id":"<id>","cursor":0,"count":20}` | `{total, has_more, cursor, comments:[…]}` | `comment_list` |
| `/api/data/replies` | `{"aweme_id":"<id>","comment_id":"<cid>","cursor":0,"count":20}` | `{has_more, cursor, comments:[…]}` | `comment_reply`（默认 nv8 真 bdms） |
| `/api/data/feed` | `{"count":10,"refresh_index":1}` | `{has_more, items:[…]}` | `aweme_feed` |
| `/api/data/user` | `{"sec_user_id":"<sec_uid>"}` | `{uid,sec_uid,nickname,unique_id,follower_count,…}` | `user_profile` |
| `/api/data/search` | `{"keyword":"…","offset":0,"count":20}` | `{has_more, items:[…]}` | `aweme_search` ⚠️ 需 www 登录态 |

统一响应（所有 6 个）：

```json
{"success": true, "status_code": 0, "message": null, "data": { }}
```

- `success` = 抖音业务 `status_code == 0`；失败时 `data` 为 `null`，看 `message`（如 `2483` 未登录、
  `非 JSON 响应（text/plain）：空 body`）。
- HTTP 码：`401` = 无 token / token 缺 `phone` / **会话不是 www 登录态**（数据项目 `--check-login`
  打 `/aweme/v1/web/notice/count/` 得 `8` → 退出码 3 + `NEED_LOGIN` → `DouyinAuthError`）；
  `400` = 无可用会话（未登录）或签名项目跑不起来；
  `200` + `success:false` = 抖音侧失败（不发 HTTP 错误码）。
- 离线自检（不发网络）：`python backend/tests/test_data_offline.py`。

> ⚠️ **数据接口要的是「会话 cookie」，不一定是「真登录」**（`detail`/`comments`/`feed`/`user`
> 匿名会被 `text/plain` 空 body 挡回，但给个带 `ttwid` 的会话就过）。
> 而 `aweme_search` 需 **`www.douyin.com` 真登录**（无登录态/会话过期 → `2483`；
> 给一份活着的 www 登录态 → `status_code=0` 返回真实作品（实测）。
> 注：同一账号再登录会使旧会话失效，缓存必须是最近一次登录的那份）。

## 开发路线

### Phase 1: 登录模块（当前）
- [x] Android 纯 UI 前端
- [x] FastAPI 后端骨架
- [x] 逆向 send_code 签名算法（`signing/send_code/分析报告.md`；发码需工件服务产 `a_bogus`）
- [x] 逆向 sms_login 签名算法（`signing/sms_login/分析报告.md`；nv8 路径无浏览器登录成功）
- [x] 后端对接两个签名项目（`core/crawler.py` + `--json-out`）
- [ ] Redis 真实接入（`cache.py` 现为内存 dict，**重启即丢登录态**）
- [ ] App ↔ 后端登录态联调（App 侧还是本地 WebView 抓 dtrait 的旧路径）

### Phase 2: 核心爬虫

签名项目（已完成，每接口一个 `signing/<name>/`）：
- [x] 视频列表 `signing/aweme_feed/` — `GET /aweme/v1/web/tab/feed/`
- [x] 视频详情 `signing/aweme_detail/` — `GET /aweme/v1/web/aweme/detail/`
- [x] 用户信息 `signing/user_profile/` — `GET /aweme/v1/web/user/profile/other/`
- [x] 评论 `signing/comment_list/` + `signing/comment_reply/`（reply 已打通：改用真 bdms a_bogus）
- [x] 关键词搜索 `signing/aweme_search/`（需 www 登录态，见下）
- [x] backend 调度层：`core/crawler.py` 加 6 个方法（`_run_data` + `_envelope`）
- [x] backend 路由：`api/data.py` 6 个明确路由 + `models/schemas.py` + JWT `phone` claim
- [x] backend 归一化：`core/normalize.py`（aweme / comment / user / aweme_list）
- [x] backend 离线自检：`tests/test_data_offline.py`
- [x] 登录态判定：数据项目 `--check-login`（`/aweme/v1/web/notice/count/`）→ 后端 401 请重新登录
- [ ] App 页面（列表 / 详情 / 评论 / 用户 / 搜索）接入 `/api/data/*`

> ⚠️ **登录态边界（实测修正）**：登录流程产出的会话**可以**是 `www.douyin.com` 的合法登录态——
> `async_session.json` 实测 `/aweme/v1/web/notice/count/` = `0`、`search` = `0`（返回真实作品）。
> 但**同一账号再次登录会让旧会话失效**：`sms_login_session.json` / `nv8_session.json` 现在都是
> `account_info error_code=13 会话过期` → `/notice/count/` = `8`、`search` = `2483`。
> 所以后端缓存里的 `dy_login:{phone}` 必须是**最近一次成功登录**的会话。
>
> 数据接口分两档：
> - 公开（`detail` / `comments` / `feed` / `user`）：只需一个带 `ttwid` 的**会话**，不要求登录。
> - 登录门控：只有 **`search`**。给 www 登录态即 `0`（实测）。
> - `replies` **不卡登录，卡签名来源**：mod.js 的 a_bogus 它不认，必须 `--abogus-source nv8`
>   （真 bdms）。证据 `signing/comment_reply/js_reverse_cache/env/reply_bdms_finding.md`。
>   nv8 建议走常驻服务（`signing/_shared/start_nv8_service.bat`，:8789）——单次 a_bogus ~20ms；
>   服务没开时 CLI 自动回落本进程起 Node（~5s）。

### Phase 3: 数据处理
- [ ] 数据清洗
- [ ] 数据存储（MySQL/MongoDB）
- [ ] 数据导出

## 运行方式

```bash
# 一次性：建后端自带 venv（不依赖系统 python）
python backend/runtime/bootstrap.py --install

# 启动后端（backend 是命名空间包，从仓库根跑；
# `cd backend && python main.py` 会因相对 import 报 ImportError）
backend/start.bat                    # Windows（自动用 backend/runtime/venv）
# 或  ./backend/start.sh               # Linux/macOS
# 或  backend/runtime/venv/Scripts/python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# 离线自检（不发网络）
python backend/tests/test_crawler_offline.py
python backend/tests/test_data_offline.py      # 数据接口离线自检（不发网络）

# 单独验签名项目（各自能跑完整个流程；--dry-run = 只组参数不发请求）
cd signing/send_code && runtime/venv/Scripts/python.exe main.py --dry-run
cd signing/sms_login && python main.py --dry-run
cd signing/send_code && python tests/test_vectors.py          # 离线固定向量
```

---

# 经验教训记录

## Bug 模式：按钮锁死（sendingInProgress 未清除）

**时间**: 2026-09-18
**问题**: 加了 `sendingInProgress` 防重复点击标志后，按钮点了没反应
**原因**: `sendingInProgress = true` 设置后，如果异步流程（dtrait捕获/发码）失败或超时，没有清除该标志的路径，按钮永远锁死
**修复**:
1. 加超时保底：`uiHandler.postDelayed(() -> sendingInProgress = false, 15000)`
2. 所有异步分支（成功/失败/超时）都必须清除该标志
3. 成功路径在 `handleLocalSms` 里清除

**教训**: 任何防重复点击的 flag，必须保证所有异步路径（成功、失败、超时、异常）都能清除它。不能只依赖成功路径。

## Bug 模式：reload 整页导致流程过慢

**时间**: 2026-09-18
**问题**: 点击获取验证码要等22秒才发送
**原因**: dtrait未就绪时 `webSendSms()` 调用 `bgView.reload()` 触发完整预热链（4s初始 + 多轮×3.5s + 6.7s capture），总计20+秒
**修复**: 改为直接调 `captureDtrait()`（约6.7秒），不reload整页
**教训**: 避免用 reload 来重试异步状态，应该用已有的轻量级重试路径

## 后端对接踩坑（2026-09-18）

### 响应契约不是 status_code/description
- **问题**: `api/auth.py` 用 `result.get('status_code',0)==0` 判成功、`data.token` 取登录态
- **结果**: 真实响应里没这些字段 → 永远 `success=True`，但 token/user_id 全是 `None`，App 拿不到登录态
- **修复**: 按真实响应取值：成功 = `message=="success"` 或 `data.error_code==0`；错误码在 `data.error_code`
- **教训**: 别照抄旧格式的字段名，先拿**一份真实响应**把契约钉死（已落在 `tests/test_crawler_offline.py`）

### 后端不该自己发抖音请求
- **问题**: `crawler.py` 原骨架准备自己用 aiohttp 发请求，只把「签名」外包
- **原因**: 实际交付形态里 `signing/{send_code,sms_login}/main.py` 已经把「组包+签名+引导会话+发请求」全做完了，
  且参数（`dtrait`/`a_bogus`/`msToken`）依赖它们自己的 nv8/浏览器工件
- **修复**: crawler 只做调度（subprocess + `--json-out`）；`core/signing.py` 因此失去调用方
- **教训**: 对接前先看对方**已经跑通的入口**，不要在它之上重建一整套重复的请求层

### 发码会话必须复用到登录
- **问题**: 登录自己新引导一个会话（新 `ttwid` = 新设备身份）→ 稳定拿 `7 访问太频繁`
- **修复**: 发码成功后 `GET 工件服务/cookies` 把「发码那条会话」缓存，登录原样当 `--cookie-file`
- **教训**: 抖音的 `7`/`2156` 是**会话/设备级**风控，不是参数错误；跨请求的动作要复用同一会话

### 测试脚本不能当生产依据
- **问题**: 曾照搬 `signing/sms_login/tests/e2e_login.py` 的「发码后必须等 95s」硬门禁
- **原因**: 那是测试脚本的启发式；`sms_login/分析报告.md` §6.8 实测浏览器 62s 提交也能成功，
  `7` 与请求者/会话强相关而不是时间阈值
- **修复**: 删掉时间门禁，`7/2156` 原样透出 `error_code + message` 交给 App 展示
- **教训**: `tests/` 里的脚本是验证手段，不是协议事实；协议只认交付入口 + 分析报告

## 界面变成了“毛坯”（2026-09-19）

**时间**: 2026-09-19
**问题**: 手机上所有页面都是白方块：方角灰按钮、没卡片、没间距层次；底部导航只有选中那个 tab 有图标
**原因**（两个独立问题叠在一起）:
1. **尺寸写了裸像素** —— `setPadding(20,20,20,20)`、`setMinWidth(200)`。本机 560dpi（1dp=3.5px），
   20px 只有 `≈5.7dp`，所有间距被压扁；而 `Ui.dp()` 就摆在那里没人用
2. **没用已有的设计系统** —— `Ui.java` 的 `field/primaryButton/ghostButton/card/sectionTitle/gridCard/listRow`
   全部未被调用，页面自己 `new Button` + `setBackgroundColor`；`res/values/colors.xml` 的 `dy_*`、
   `styles.xml` 的 `DyField/DyButtonTeal`、`layout/page_login.xml` 的青绿设计也全没用
3. **导航选中靠隐藏整颗药丸** —— `pill` 里装着图标，`pill.setVisibility(INVISIBLE)` 把未选中 tab 的图标一起藏了

**修复**: 页面改用 `Ui.*` 组件 + 全部尺寸走 `Ui.dp()`；导航改成“图标始终可见，只切药丸背景和文字颜色”；
登录页按 `res/layout/page_login.xml` 做（青绿 Header + 白色上圆角卡片 + 130x46 青绿药丸按钮）

**验证**: `adb exec-out screencap` + `uiautomator dump` 看 bounds：
标题/输入框左边缘一致 `77px≈22dp`、输入框高 `150px≈43dp`、四个 tab 图标均在（各 `84px=24dp`）

**教训**: 改 UI 前先看 `Ui.java` 和 `res/values/` —— 这个项目已经有设计系统，页面只负责“拼”；
新页面上线前用 `uiautomator dump` 对一遍 bounds，比肉眼判断可靠

## 开发规范

### `.bat` 必须 CRLF + 纯 ASCII 注释
- Windows `cmd.exe` 只认 **CRLF**；LF-only 会让它解析错行，把 UTF-8 中文注释当命令执行，
  报 `'渚濊禆绯荤粺' 不是内部或外部命令`（GBK 解码出来的“依赖系统”）。
- `.bat` 注释一律写英文/ASCII（cmd 按 OEM 码页解码，中文必乱码）；`.sh` 保持 LF。
- 排查：`python -c "b=open('x.bat','rb').read(); print(b.count(b'\r\n'), b.count(b'\n')-b.count(b'\r\n'))"`
  （第二项应为 0）。

### 添加防重复/锁状态时
- 必须在所有异步路径清除 flag（成功 + 失败 + 超时 + catch）
- 加超时保底兜底
- 用 Log.i("DYSTEP", ...) 标记关键步骤方便 logcat 排查

### 前端调后端：先看 success，不是看 HTTP 200
- 后端业务失败也是 **HTTP 200 + `success:false`**（`2156` 系统繁忙 / `1203` 码错 / `7` 风控）
- 判成功必须读 JSON：`Api.jsonBool(text, "success")`（布尔值不能用 `jsonValue`/`jsonNumber`）
- 提示语顺序：`message`（业务失败）→ `detail`（参数错误 400）→ 兵底文案
- 倒计时秒数取后端 `retry_after`（= 抖音 `retry_time`），拿不到才回退 60s

### 登录态：两套视图切换，不要“灰掉”了事
- 登录页在 `buildLogin()` 里建两个容器：`formBox`（手机号/验证码/获取验证码/登录）与
  `loggedBox`（账号块 + 退出登录），由 `updateLoginStatus()` 按登录态互斥显示
- 登录后**不能再看到手机号/验证码这些“未登录”控件**，也不要只把它们 `setEnabled(false)`
- 账号信息从 SharedPreferences 取（`login_phone` / `login_user_id`）；老数据只有 token 时，
  用 `userIdFromToken()` 从 JWT payload base64 解出 user_id（签名始终由后端校验）
- 顶部状态行（已登录/未登录）与主页快捷入口的文案也要跟着变 —— 状态只在一个地方算

### 发码按钮：一个状态而非三个
- **反例**: `sendingInProgress` + `setEnabled` + 倒计时分开维护 → 漏清就锁死（见上面 Bug 模式）
- **现做法**: 只留 `sendCooldown` 一个 int（>0 = 冷却中），按钮禁用/文案/防重点击全由它派生：
  `startCooldown(60)` → 每秒 -1 显示 `60s后发送` → 到 0 `resetSendCodeBtn()`
- 失败路径（业务失败/网络错误/400）也要 `resetSendCodeBtn()`，否则按钮停在"发送中..."

### 修改按钮行为时
- 先看完整个调用链再改，不要只改一个点
- 用 `adb logcat -s DYSTEP` 验证实际流程

### 选择器陷阱（2026-09-18）
- **问题**: `dyRect('login')` 用 `pick('登录')` 匹配到了导航栏文本，不是真正的登录按钮
- **原因**: 页面有多个 `登录` 文本（导航栏链接、弹窗内按钮），`pick()` 只返回第一个匹配
- **修复**: 遍历所有 `button/div[role=button]/a` 元素，按文本+尺寸过滤（`width>=40, height>=20`），跳过 `offsetParent===null`
- **教训**: 页面文本选择器必须考虑同名元素，需要加尺寸/位置约束

### dyState 状态检测（2026-09-18）
- **问题**: `dyState` 返回 `phone:false` 即使弹窗已打开
- **原因**: `dyState` 检查 `input` 元素的 `placeholder`，但 placeholder 文本可能变化
- **修复**: 同时检查 `placeholder` 和 `aria-label`，并输出 inputs 数组调试
- **教训**: 检测 DOM 状态时，要输出完整的匹配结果（如 inputs 数组），不要只输出布尔值

### dtrait 捕获时机（2026-09-18）
- **问题**: dtrait 轮询8秒超时
- **原因**: challenge 端点（`/passport/web/challenge/`）在弹窗打开后才触发，首次弹窗打开需要约9秒
- **修复**: 将 `doCaptureDtrait` 轮询超时增加到15秒；warmup 最大轮次增加到12轮
- **教训**: dtrait 依赖的 challenge 端点由前端 JS 自主发起，时间不可控，轮询超时要留足够余量
- **关键发现**: dtrait 通过 `setRequestHeader` 钩子捕获（`x-tt-session-dtrait`），不是从 URL 或 body 中提取

### fetch hook 不要覆盖 dtrait（2026-09-18）
- **问题**: fetch hook 中 `get('x-tt-session-dtrait')` 返回 `"undefined"` 时覆盖了已有的 dtrait
- **原因**: `Headers.get()` 找不到 key 时返回 `null`，`String(null)` = `"null"`，但 `undefined` 被转成 `"undefined"` 字符串
- **修复**: `if(dv){ grabDt(...) }` — 只有非空值才调用
- **教训**: `String(undefined)` = `"undefined"`，不是空字符串。fetch 的 headers.get() 可能返回 null/undefined，必须判断
