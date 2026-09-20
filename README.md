# 抖音数据采集（Douyin Spider）

抖音 Web **纯协议复现**：短信验证码登录链路 + 6 个数据接口，配 FastAPI 后端 + Android 前端。

不抓包、不用 App，纯 HTTP 打通：`send_code` 发码 → `sms_login` 登录 → 拿到
`sessionid` / `sid_guard` / `x_tt_token` 等真实登录态；再用同一份会话，由 6 个独立签名项目
分别取**视频详情 / 评论列表 / 评论回复 / 视频列表 / 用户信息 / 关键词搜索**。
后端只负责缓存登录态并调度签名项目。

> ⚠️ 仅供学习与安全研究。请只用自己的号码调试，详见文末[免责声明](#免责声明)。

---

## 架构

```
Android App (纯 Java UI)
     │ HTTP + JSON（登录传 phone/code；数据接口带 Bearer JWT）
     ▼
FastAPI 后端              api/auth.py    登录路由 + JWT
                          api/data.py    数据 6 路由（手机号从 JWT 取）
                          core/crawler.py   调度（subprocess + 全局锁 + 内存缓存）
                          core/normalize.py 原始响应 → 扁平记录
     │ subprocess 调 signing/*/main.py            ← 唯一 HTTP 出口
     ├─ 登录类（需浏览器 / nv8 工件）
     │   signing/send_code   参数 → a_bogus（浏览器 bdms 现场签）→ /passport/web/send_code/
     │   signing/sms_login   参数 → a_bogus（nv8 跑页面同款 bdms 字节码）→ /passport/web/sms_login/
     │
     └─ 数据类（只需 a_bogus + 会话 cookie，共用 signing/_shared）
         aweme_detail   comment_list   comment_reply
         aweme_feed     user_profile   aweme_search
              └────────► /aweme/v1/web/*（replies 必须真 bdms，其余 mod.js 即可）
     ▼
抖音 login.douyin.com · www.douyin.com
```

**几个关键设计**

- **后端自己不发抖音请求**：参数、签名、发请求全在 `signing/` 各项目里完成，后端只用
  `subprocess + --json-out` 调度（比解析 stdout 稳，stdout 有截断）。
- **发码会话必须复用到登录**：`a_bogus` 绑会话，换一个会话（新 `ttwid` = 新设备身份）
  登录会被判 `7 访问太频繁`。后端会缓存发码那条会话给登录用。
- **`a_bogus` 只有一份**（`signing/_shared/node/mod.js`）：6 个数据接口共用，不再各自复制。
- **数据接口分三档**：公开（detail/comments/feed/user，只要带 `ttwid` 的会话）、
  登录门控（search，无登录态返回 `2483`）、签名挑食（replies 只认真 bdms，mod.js 的
  a_bogus 它不认）。

---

## 仓库结构

```
douyin_spider/
├── backend/              FastAPI：路由 + JWT + 调度 + 登录态缓存（不发抖音请求）
│   ├── api/auth.py       POST /api/auth/send_code · /api/auth/sms_login
│   ├── api/data.py       ★ POST /api/data/{detail,comments,replies,feed,user,search}
│   ├── core/crawler.py   ★ subprocess 调 signing，归一化响应、缓存会话/登录态
│   ├── core/normalize.py 原始响应 → 扁平记录（丢掉 100KB+ 的无用字段）
│   ├── core/cache.py     内存缓存（接口同 Redis，重启即丢）
│   └── runtime/bootstrap.py  建后端 venv + 装依赖
│
├── signing/              签名与请求（各自独立项目）
│   ├── _shared/          ★ 6 个数据接口共用的参数/签名/HTTP 层（唯一一份）
│   │   ├── params.py     公共参数 COMMON_PARAMS + build_url
│   │   ├── signer.py     pyexecjs2 → node/mod.js（a_bogus，快）
│   │   ├── nv8.py        真 bdms a_bogus（replies 必须用；复用 sms_login 的工件）
│   │   ├── nv8_service.py ★ 常驻 nv8 服务（:8789，单次 ~20ms；没开则回落起 Node ~5s）
│   │   ├── http.py       cookie 载入 / 请求头 / 发请求 / 登录态检查（--check-login）
│   │   └── cli.py        通用命令行开关
│   │
│   ├── send_code/        发码：浏览器 bdms 现场签 a_bogus；自带 venv + node
│   │   ├── main.py       ★ 交付入口（端到端）
│   │   ├── node/         signer_server.mjs（常驻参数服务）+ mod.js
│   │   ├── utils/        passport / dtrait / artifact_service / signer
│   │   ├── assets/       dtrait_core.js · RSA 公钥 · sm3 · abogus
│   │   └── 分析报告.md    参数逆向报告（定位 / 分类 / 阻塞点与结论）
│   │
│   ├── sms_login/        登录：nv8 签 a_bogus，全程无浏览器
│   │   ├── main.py       ★ 交付入口（默认 --abogus-source nv8）
│   │   ├── node/         abogus_server.mjs · dtrait_server.mjs
│   │   ├── utils/        passport / nv8_signer / dtrait / dtrait_signer
│   │   └── 分析报告.md    登录已打通报告
│   │
│   ├── aweme_detail/     视频详情   /aweme/v1/web/aweme/detail/
│   ├── comment_list/     评论列表   /aweme/v1/web/comment/list/
│   ├── comment_reply/    评论回复   /aweme/v1/web/comment/list/reply/（端点级反爬）
│   ├── aweme_feed/       视频列表   /aweme/v1/web/tab/feed/
│   ├── user_profile/     用户信息   /aweme/v1/web/user/profile/other/
│   ├── aweme_search/     关键词搜索 /aweme/v1/web/search/item/（需 www 登录态）
│   │   └── 每个数据项目 = main.py + config.local.json + tests/ + output/
│   │
│   ├── check_data_interfaces.py  6 个接口一键实测（走真实交付入口）
│   └── 接口自测指南.md
│
├── end_test/             后端联调脚本（login_test.py + 6 个数据 *_test.py）
│
└── android/              纯 Java UI 前端（自建 build.py，无需 Gradle）
    ├── build.py          构建脚本：aapt2 / d8 / zipalign / apksigner
    ├── app/src/main/java/com/douyin/spider/
    │   ├── MainActivity.java   主页 / 数据 / 存储 / 我的（发码 60s 倒计时、登录态两套视图）
    │   ├── Api.java            HTTP 客户端
    │   └── Ui.java             设计系统（尺寸走 Ui.dp()，配色在 res/values/colors.xml）
    ├── AGENTS.md           整体架构 / 接口契约 / 踩坑记录
    └── PROJECT_GUIDE.md
```

各部分的详细文档：
[`backend/README.md`](backend/README.md)（启动/排错/接口契约）·
[`signing/_shared/README.md`](signing/_shared/README.md)（数据接口共用层）·
[`signing/接口自测指南.md`](signing/接口自测指南.md)（6 接口逐项手测）·
[`signing/send_code/README.md`](signing/send_code/README.md) ·
[`signing/sms_login/README.md`](signing/sms_login/README.md) ·
[`android/AGENTS.md`](android/AGENTS.md)

---

## 快速开始

### 一键更新

使用 `git clone` 安装项目后，可随时运行根目录的更新器拉取最新进度：

```bat
:: Windows：双击 update.bat，或在终端运行
update.bat
```

```bash
# macOS / Linux
./update.sh
```

更新器只接受 Git 仓库且无本地代码改动的项目，并使用 `git pull --ff-only` 安全更新；
被 `.gitignore` 忽略的本地配置、登录态和运行文件不会被删除。

### 1. 后端

```bash
# 在仓库根执行（backend 是命名空间包，cd backend 会 ImportError）
python backend/runtime/bootstrap.py --install      # 建 venv + 装依赖（含数据接口所需依赖）
backend/start.bat                                  # Windows；Linux/macOS 用 ./backend/start.sh
# 等价手动：
#   backend/runtime/venv/Scripts/python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

curl http://127.0.0.1:8000/health        # {"status":"ok"}
```

浏览器打开 `http://127.0.0.1:8000/docs` 可直接填表调用。

### 2. 签名项目

**登录类**共用 `signing/*/config.local.json`（**未入库**，需自己建）：

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

**数据类**（`aweme_detail` 等 6 个）用**后端 venv**（`crawler._python()` 回落），
配置只认 `cookie_file` / `verify_tls`：

```bash
# 离线：只组参数 + 签名，不发请求
cd signing/aweme_detail
python main.py --aweme-id 7626316866109066511 --dry-run --verbose

# 真实请求（需要一份带 ttwid 的会话 cookie）
python main.py --aweme-id 7626316866109066511 --cookie-file <ck> --check-login
```

评论回复要真 bdms，建议挂常驻服务（单次 ~20ms，否则每个 replies 多 ~5s）：

```bat
signing\_shared\start_nv8_service.bat        REM 常驻 127.0.0.1:8789
```
```bash
# 6 接口一键实测（走各项目真实交付入口）
cd signing
python check_data_interfaces.py --cookie-file <cookie>
```

### 3. Android

```bash
cd android
python build.py --server-url http://192.168.1.100:8000   # 真机填局域网 IP
# 模拟器不用传：默认 http://10.0.2.2:8000
adb install -r douyin-spider.apk
```

### 4. 自检（离线，不发网络）

```bash
python backend/tests/test_crawler_offline.py       # 登录：响应契约 + CLI 接线
python backend/tests/test_data_offline.py          # 数据：normalize + _envelope + 6 项目调度
cd signing/_shared && python tests/test_vectors.py # 6 条 a_bogus 冻结向量 + 登录判定
cd signing/send_code && runtime/venv/Scripts/python.exe tests/test_vectors.py
cd signing/sms_login  && python tests/test_vectors.py
```

### 5. 联调（对真实后端发请求）

```bash
cd end_test
python login_test.py          # 发码 + 登录，成功自动把 token 写进 token.txt
python detail_test.py         # 再跑数据接口脚本（自动带 token.txt 里的 JWT）
```

---

## 接口

### 登录（`/api/auth/*`，无需 token）

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

### 数据（`/api/data/*`，需 `Authorization: Bearer <登录返回的 JWT>`）

手机号从 JWT 的 `phone` claim 取，后端据此在缓存里找会话 cookie，再传给签名项目。

| 方法 | 路径 | 请求体 | `data` 形状 |
|------|------|--------|-------------|
| POST | `/api/data/detail` | `{"aweme_id":"<id>"}` | 作品摘要（aweme_id/desc/author/statistics/duration） |
| POST | `/api/data/comments` | `{"aweme_id":"<id>","cursor":0,"count":20}` | `{total, has_more, cursor, comments:[…]}` |
| POST | `/api/data/replies` | `{"aweme_id":"<id>","comment_id":"<cid>","cursor":0,"count":20}` | `{has_more, cursor, comments:[…]}` |
| POST | `/api/data/feed` | `{"count":10,"refresh_index":1}` | `{has_more, items:[…]}` |
| POST | `/api/data/user` | `{"sec_user_id":"<sec_uid>"}` | 用户信息（uid/nickname/unique_id/follower_count…） |
| POST | `/api/data/search` | `{"keyword":"…","offset":0,"count":20}` | `{has_more, items:[…]}` ⚠️ 需 www 登录态 |

```bash
curl -X POST http://127.0.0.1:8000/api/data/detail \
     -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
     -d '{"aweme_id":"7626316866109066511"}'
# -> {"success":true,"status_code":0,"message":null,"data":{...}}
```

统一响应：`{"success":bool,"status_code":int|null,"message":str|null,"data":object|null}`。
`status_code` 是抖音业务码（`0` 成功）；`success=false` 时 `message` 给原因
（`2483` 未登录 / 空 body 被反爬 等）。

### 错误码

| 场景 | HTTP | 含义 |
|---|---|---|
| 缺字段 | `422` | pydantic detail |
| 参数/环境问题、无可用会话 | `400` | 此时**不会发起抖音请求** |
| 无 token / token 缺 phone / **会话不是 www 登录态** | `401` | 请重新登录 |
| 抖音侧业务失败 | `200` | 读 `success` 字段 |

**业务失败也是 HTTP 200**，调用方必须读 `success`，不能只看状态码。

| `error_code` | 含义 |
|---|---|
| — | 成功 |
| `1203` | 验证码错误 / 过期 |
| `2156` | 系统繁忙（端点级风控） |
| `7` | 访问太频繁（**会话或设备级风控，不是参数错误**） |
| `2483` | 搜索接口未登录 |
| `8` | 会话未登录 / 已过期（`--check-login` 判据） |

---

## 技术要点

| 环节 | 做法 |
|------|------|
| `enc` / `sign` / `qs` / `aid-sign` | 纯 Python 复现，与抓包逐位一致（`utils/passport.py`） |
| `x-tt-session-dtrait` | RSA-2048 包 `key‖iv` + AES-128-CBC（`utils/dtrait.py`） |
| `a_bogus`（发码） | 浏览器页面 `bdms` 现场签（XHR 被拦，不发业务请求） |
| `a_bogus`（登录） | **nv8 里跑页面同款 bdms 字节码**，无浏览器 |
| `a_bogus`（数据） | 共用 `_shared/node/mod.js` 公开移植版（~0.5s）；replies 走 nv8 真 bdms |
| nv8 常驻服务 | `_shared/nv8_service.py`（:8789），Node/bdms 只启一次，单次 ~20ms |
| 数据响应 | `core/normalize.py` 集中还原成扁平记录，不把原始大 payload 丢给 App |
| 登录态检查 | 数据项目 `--check-login` 先打 `/notice/count/`，`!=0` → 退出码 3 → 后端 401 |
| 后端 ↔ 签名 | `subprocess + --json-out` 落 JSON（比解析 stdout 稳） |
| 阻塞调用 | `asyncio.to_thread`（CLI 是同步的，不能卡事件循环） |
| 并发 | 登录用全局 `asyncio.Lock`（工件服务只有一条浏览器会话）；数据接口各自独立、不加锁 |

---

## 开发路线

**Phase 1 · 登录模块** ✅
- [x] Android 纯 UI 前端
- [x] FastAPI 后端骨架
- [x] 逆向 `send_code` 签名算法
- [x] 逆向 `sms_login` 签名算法（nv8 路径无浏览器登录成功）
- [x] 后端对接两个签名项目
- [ ] Redis 真实接入（`cache.py` 现为内存 dict，重启即丢登录态）
- [ ] App ↔ 后端登录态联调

**Phase 2 · 核心爬虫** ✅（协议层已通）
- [x] `signing/_shared` 数据接口共用参数/签名层
- [x] 视频详情 `signing/aweme_detail`
- [x] 评论列表 `signing/comment_list`
- [x] 评论回复 `signing/comment_reply`（需真 bdms / nv8 常驻服务）
- [x] 视频列表 `signing/aweme_feed`
- [x] 用户信息 `signing/user_profile`
- [x] 关键词搜索 `signing/aweme_search`（需 www 登录态）
- [x] 后端 6 个数据路由 + `normalize.py` + 离线自检
- [ ] App 页面（列表 / 详情 / 评论 / 用户 / 搜索）接入 `/api/data/*`

**Phase 3 · 数据处理** — 清洗 / 存储（MySQL·MongoDB）/ 导出

---

## 免责声明

本项目仅用于**个人学习、协议分析与安全研究**。

- `send_code` 会给目标号码**发送真实短信**并消耗风控额度，`sms_login` 会消耗验证码，
  请**只对自己的号码**使用，不要用于扫描他人号码。
- `signing/*/assets/` 中的 `webmssdk`、`bdms` 等 JS 版权归字节跳动所有，仅作逆向分析留存，
  请勿再分发或商用。
- 数据接口请只采集公开数据，且控制频率；禁止用于批量注册、账号交易、爬取他人隐私数据
  或任何违反 [抖音用户协议](https://www.douyin.com/agreements/) 与当地法律法规的用途。
- 使用本项目产生的一切后果由使用者自行承担。
