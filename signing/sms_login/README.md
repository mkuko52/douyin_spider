# 抖音 Web 短信验证码登录接口还原（`/passport/web/sms_login/`）

`POST https://login.douyin.com/passport/web/sms_login/` 的参数生成与调用实现。

- 逆向结论、参数分类、验证结果 → **`分析报告.md`**
- 结论：**已打通，全程无浏览器** —— `python main.py --mobile <号码>` 实测登录成功
  （`message: "success"`，下发 `sessionid` / `sid_guard` / `x_tt_token`）。
- `a_bogus` 由 **nv8 里跑页面同款 bdms 字节码**生成（默认）；
  `sign`/`qs`/`aid-sign`/`enc`/body/`msToken`/`dtrait` 已全部逐位对齐浏览器。
- **全程异步**：HTTP 用 `aiohttp`，Node 服务用 `asyncio` 子进程 + 锁（与 `send_code` 一致）。

## 目录

```
main.py                 总装入口：引导会话 → 组参数 → Node 生成 a_bogus → 发请求 → 打印响应
node/mod.js             a_bogus 生成器（pyexecjs2 用；公开移植版，服务端不认）
node/abogus_server.mjs  nv8 + 页面同款 bdms 字节码 → a_bogus（**默认来源**）
node/dtrait_server.mjs  nv8 补环境：现场采集 dtrait 设备指纹 payload
assets/                 bdms / webmssdk / dtrait_core（JSVMP）+ RSA 公钥
utils/passport.py       enc / sign / qs / aid-sign / 公共参数 / body（纯 Python）
utils/nv8_signer.py     Python → Node(nv8) 桥（a_bogus）
utils/signer.py         pyexecjs2 桥（mod.js，备用）
utils/browser_artifacts.py 真实浏览器窄工件生成器（备用 a_bogus 来源）
utils/dtrait.py         dtrait 拼头：RSA-2048 包 key‖iv + AES-128-CBC
utils/dtrait_signer.py  Python → Node(nv8) 桥（dtrait payload）
utils/logger.py         日志
tests/test_vectors.py   10 项离线固定向量验证
tests/e2e_login.py      跨项目端到端：send_code 发码 → 输入验证码 → sms_login 登录
config.local.json       本地配置（mobile / code / cookie_file / verify_tls）
js_reverse_cache/       证据（抓包样本 / 逆向笔记 / 探测脚本）
```

## 快速开始

```bash
pip install -r requirements.txt     # aiohttp / pyexecjs2 / cryptography

python main.py                                  # 默认 nv8：完全无浏览器，交互式输手机号+验证码
python main.py --mobile 138xxxxxxxx --code 123456   # 带参则跳过提问
python main.py --abogus-source browser          # 改用真实浏览器产 a_bogus（需 playwright）
python main.py --dry-run                        # 只生成参数与 URL，不发请求
python tests/test_vectors.py                    # 离线固定向量（不发网络）
```

`nv8` 需要一个 nv8 运行时（默认 `D:/develop_software/nv8/src/index.js`，可用 `NV8_SRC` 覆盖）。

## 全程异步

与 `send_code` 项目一致：

| 层 | 实现 | 并发安全 |
|---|---|---|
| HTTP 出口 | `aiohttp`（`async with session.post(...)`） | ✅ 天生异步 |
| Node 参数服务（bdms / dtrait） | `asyncio.create_subprocess_exec` + `asyncio.Lock` | ✅ 锁内串行 |
| 浏览器窄工件（可选） | `AsyncBrowserArtifacts`（`playwright.async_api`） | ✅ 原生异步 |
| pyexecjs2（`modjs` 备用） | `asyncio.to_thread` | ✅ 同上 |

`main.py` 入口是 `asyncio.run(_amain())`。

取值优先级：`命令行 > 交互输入 > config.local.json > 内置默认`。
非交互场景（管道 / CI）`input()` 读不到东西时会自动回退到 config / 默认，不会卡住脚本。

## 分工

| 侧 | 职责 |
|---|---|
| Node + **nv8**（`node/abogus_server.mjs`） | 跑页面同款 **bdms 字节码**生成 `a_bogus`（不发网络） |
| Node + **nv8**（`node/dtrait_server.mjs`） | 采 `dtrait` 设备指纹 payload（不发网络） |
| Python（`main.py` + `utils/`） | 引导会话、组 query/body/headers、`sign`/`qs`/`enc`/`aid-sign`/RSA+AES、**独占 HTTP 出口** |

**默认完全无浏览器**。`--abogus-source browser` 也保留（用真实浏览器产 a_bogus，同样实测成功）。

### 为什么 `a_bogus` 必须用 bdms

`a_bogus` 是 bdms（字节码 VM）的产物。公开移植版（`node/mod.js`）算法不对，
服务端在**有效验证码**下会判 `7 访问太频繁`（无效码则停在 `1203`，看上去像“通过”，
这是个陷阱）。用 nv8 把页面同款 bdms 资源跑起来后，服务端就接受。

> 注意：`a_bogus` **本身带随机分量** —— 同一 query 连签两次值就不同，
> 所以不能用“与浏览器逐位对比”来验收，**只能看服务端是否接受**。

### nv8 补环境框架

`uc-secure-dtrait-core`（`assets/dtrait_core.js`）是 JSVMP 库，会读 `navigator` /
`screen` / canvas / WebGL 等浏览器特征，**裸 Node 跑不了**。
`node/dtrait_server.mjs` 用 **nv8**（`D:\develop_software\nv8`）把这套环境补到“检测不出来”，
现场采集设备指纹 payload；RSA/AES 加密仍由 Python 完成（`utils/dtrait.py`）。

```bash
NV8_SRC=D:/develop_software/nv8/src/index.js   # 覆盖 nv8 入口（默认就是它）
NV8_NODE=<node.exe>                            # 覆盖 node
DTRAIT_TTL=86400                               # payload 磁盘缓存 TTL（设备级、稳定）
```

## 响应含义

| `error_code` | 含义 | 怎么办 |
|---|---|---|
| `0` + `message: success` | **登录成功**，会话 cookie（`sessionid` 等）已下发 | 完成 |
| `1203` | 验证码错误 / 过期 → **参数层已通过**（与浏览器一致） | 换新验证码 |
| `7` | **访问太频繁**：请求已被受理 | 等 **≥90s** 再试；若已提交过同一个码，该码已作废 |
| `2156` | 系统繁忙 / 风控拦截（会话不全或调用过密） | 换会话 / 等一会儿 |

### 时序规律（部分成立）

同一个验证码**只能提交一次**：任何一次提交（包括被 `7` 拒掉的那次）都会把码作废，
之后拿同一个码提交只能拿到 `1203 验证码过期`。

关于 `7`：**早期结论（“发码后 <90s 必得 `7`”）已被推翻** ——
浏览器在发码后 **62s** 提交并**登录成功**。已确认的不是时间阈值，而是**请求方差异**：
同一时段内，浏览器能成功，我们的请求会被 `7` 挡下。详见 `分析报告.md` 第 6.5 节。

实践结论：

1. **一个号码只做一次尝试**，别重试（重试会把码废掉）；
2. `7` / `1203` / `2156` **都不是参数/签名错误**；
3. 当前待定位的差异：`dtrait` 设备画像（我们 `2/344/896` vs 浏览器 `2/344/472`）
   与 `x-tt-passport-verify-portrait`（浏览器与发码时同 UUID）。

## 会话复用（重要）

每次 `python main.py` 都会重新引导会话，即**新注册一个 ttwid = 新设备身份**。
对同一个号码反复用新身份登录会很快撞上 `7` / `2156`。复用同一会话可明显降低风险：

```bash
python main.py --cookie-file js_reverse_cache/private/session.json \
               --save-cookies js_reverse_cache/private/session.json
```

`--save-cookies` 写的是**会话凭证**，默认不写盘，只在显式指定时写；请放在
`js_reverse_cache/private/`（已 gitignore）。

## 跨项目端到端（发码 → 登录）

验证码需要由另一个项目 `../send_code` 发送。两个项目在**真实场景里是分开的**，
所以 `tests/e2e_login.py` 只用 `subprocess` 调用它、不 import 任何模块：

```bash
# 完整流程：调 send_code 真发一条短信 → 提示输入验证码 → sms_login 登录
python tests/e2e_login.py --mobile 138xxxxxxxx

# 已经收到验证码了：跳过发码
python tests/e2e_login.py --mobile 138xxxxxxxx --skip-send

# 只验证接线，不发任何真实请求
python tests/e2e_login.py --mobile 138xxxxxxxx --code 123456 --skip-send --dry-run
```

删除 `tests/e2e_login.py` 不影响两个项目各自独立运行。

## 注意

- 该接口是**登录**动作，是真实短信验证码登录；请只对自己的号码使用。
- 连续调用会累积风控（`7` / `2156`），请勿高频调用。
- 只用于授权范围内的接口分析与自有账号验证。

## 复现实验（诊断脚本，非交付路径）

```bash
# a_bogus 单变量 A/B：浏览器现场签名 vs node/mod.js 签名
..\send_code\runtime\venv\Scripts\python.exe js_reverse_cache\recon\isolate_sms_login.py

# cookie 子集扫描
python js_reverse_cache\recon\bisect_cookies.py <storage_state.json>
```
