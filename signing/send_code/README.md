# 抖音 Web `send_code` 接口逆向

`POST https://login.douyin.com/passport/web/send_code/` 的参数生成与调用实现。

- 参数生成位置、固定/动态分类、阻塞点分析 → **`分析报告.md`**
- 结论一句话：参数层已完全还原（`sign`/`qs` 与抓包逐位一致），业务层被
  `bd_ticket_guard` 请求级签名拦住（`2156`）。

## 目录

```
main.py                 总装入口：组参数 → 调 Node → 发请求 → 打印响应
node/signer_server.mjs  常驻参数服务（dtrait 现场采集 + a_bogus）
node/mod.js             还原的 a_bogus 签名器
utils/passport.py       enc / sign / qs / aid-sign（纯 Python）
utils/dtrait.py         x-tt-session-dtrait 组装（RSA-2048 + AES-128-CBC）
utils/signer.py         Python → Node 桥
assets/                 dtrait 核心、RSA 公钥、sm3、abogus
runtime/                项目自带 venv + node（不依赖本机环境变量）
tests/test_vectors.py   9 项固定向量验证
js_reverse_cache/       证据（样本 / 逆向笔记 / 探测脚本 / 会话态）
```

## 快速开始

```bash
# ★ 默认 auto：有常驻服务就用它；没有就自动拉起一个（首次 ~2.5-6s）
#   之后每次调用 ~0.7-1.4s（a_bogus 本身 ~10ms）。浏览器默认 **无头**。
python main.py

# 显式走常驻服务（先手动起服务，适合批量）
start_service.bat                     # 或 ./start_service.sh
python main.py --abogus-source service

# 只想生成参数、不发请求
python main.py --dry-run

# 完全无浏览器（nv8 自产 a_bogus）——参数全部正确，但服务端当前拒收该 a_bogus
python main.py --abogus-source nv8

# 只生成参数，不发请求
python main.py --dry-run

# 换目标号码（覆盖 config.local.json）
python main.py --mobile 139xxxxxxxx

# 离线固定向量（不发网络）
python tests/test_vectors.py

# 想用项目自带运行时（venv + node 都不依赖本机环境变量）
runtime\venv\Scripts\python.exe runtime\bootstrap.py --install   # 只需一次
runtime\venv\Scripts\python.exe runtime\run.py                   # 等价于 python main.py
```

## 两种 a_bogus 来源

| `--abogus-source` | 说明 | 服务端是否接受 |
|---|---|---|
| `service`（最快） | 调用常驻工件服务（`start_service.bat`）。浏览器/Node 只启一次，**每次调用 ~1.6s**，a_bogus 本身 ~11ms | ✅ 实测 `success` |
| `browser`（**默认**） | 用 playwright 打开真实页面，让页面上的 **bdms** 生成 `a_bogus`；请求在 `send` 处**被拦下**，只取签名后的完整 URL。浏览器仅作**窄工件生成器**，**Python 独占 HTTP 出口** | ✅ **实测 `message:success`** |
| `nv8` | 完全无浏览器：nv8 里跑 bdms 字节码 VM 生成 `a_bogus`。环境/资源/初始化/共享全局都已对齐到逐字节一致 | ❌ 服务端仍返回 `2156` |

> 原因见 `js_reverse_cache/env/env_zero_diff_final.md`：环境值差异已归零，
> 但 nv8 的 bdms 与页面 bdms 输出仍不等价（疑与 bdms 内部状态/冷热有关）。

`browser` 形态的前置：`pip install playwright`（已含在 venv）+ 本机 Chrome。

## 配置

`config.local.json`（命令行参数优先于它）：

```json
{
  "mobile": "13000000000",
  "cookie_file": "js_reverse_cache/private/browser_state.json",
  "verify_tls": false
}
```

`mobile` 缺省是**非可投递占位号**，所以 `python main.py` 能直接跑完且不骚扰真实用户；
换成真号前请确认那是你自己的号码（该接口会发**真实短信**并消耗风控额度）。

## 响应效率

| 形态 | 单次 dry-run | 说明 |
|---|---|---|
| **`auto`（默认）** | **冷 ~2.5–6s，热 ~0.7–1.4s** | 自动拉起/复用常驻服务；a_bogus 本身 ~10ms |
| `service`（已起服务） | ~0.7–1.4s | 同上，但不自动拉起 |
| `browser`（每次启无头浏览器） | ~3.6–4.0s | 浏览器启动+页面加载+SDK就绪 ~3s |
| `nv8`（无浏览器） | ~5.3s | Node+nv8 沙箱启动 ~4.7s |

两处关键优化：

1. **dtrait payload 磁盘缓存**（`js_reverse_cache/private/dtrait_payload_cache.json`，TTL 24h）——
   设备指纹稳定，页面在同一会话里也复用；首次 ~4.7s，之后 0 开销。TTL 可用 `DTRAIT_TTL` 覆盖。
2. **常驻工件服务** —— 把浏览器与 Node 的启动成本从"每次"变成"一次"。

> 浏览器默认**无头**（headless）。注意必须把 UA 覆盖成正常 Chrome
> （无头 Chrome 的 UA 带 `HeadlessChrome`，而 bdms 会检测该字符串并把它编进签名）。

## 运行形态：全程异步

| 层 | 实现 | 并发安全 |
|---|---|---|
| HTTP 出口 | `aiohttp`（`async with session.post(...)`） | ✅ 天生异步 |
| 浏览器工件 | `playwright.async_api`（`AsyncBrowserAbogus`） | ✅ **页面池 + 每页一把 `asyncio.Lock`**（默认 4 页） |
| 常驻工件服务 | `aiohttp.web`（`async def` handlers） | ✅ 同一把池锁串行化单页 |
| Node 参数服务 | `asyncio.create_subprocess_exec` + `asyncio.Lock` | ✅ 锁内串行 |

> **为什么要页面池**：一次 `a_bogus` 的生成靠页面里的 `window.__bab` 做「请求 → 签名 → 交接」。
> 单页并发会互相覆盖这个交接状态（实测 6 并发只有 **1/6** 正确）。
> 池化后实测 **32 并发 79ms（~2.5ms/个）· 100% 正确**。

`main.py` 内部为 `async def`，入口 `main()` 用 `asyncio.run()` 驱动。
依赖见 `requirements.txt`：`aiohttp` / `playwright` / `cryptography`（`requests` 仅保留给 recon 脚本）。

### 工件服务接口（全异步）

| 方法 | 路径 | 参数 | 返回 |
|---|---|---|---|
| GET | `/health` | — | `{ok, uptime, counts}` |
| GET | `/cookies` | — | `{cookies}`（**签名同一浏览器会话**的 cookie） |
| POST | `/abogus` | JSON：`url`（**必填**）、`method`（可选，默认 `POST`）、`body`（可选，**参与签名**） | `{signed_url, a_bogus, ms, page_url}` |
| POST | `/dtrait` | — | `{payload}` |

启动：`start_service.bat [--port 8787] [--pages 8]`

## 分工

| 侧 | 职责 |
|---|---|
| Node（nv8 + `mod.js`） | 生成参数：`dtrait` 设备指纹 payload、`a_bogus`。**不发网络** |
| Python | 组装 query/body/headers，`sign`/`qs`/`enc`/`aid-sign`/`dtrait` 加密，**独占 HTTP 出口** |

Node 运行时用 nv8 是因为 `uc-secure-dtrait-core` 会读取大量浏览器环境特征
（`navigator`/`screen`/canvas/WebGL），裸 Node 跑会降级成错误指纹。

## 合规

- 只用于授权范围内的接口分析与自有账号验证。
- `python main.py` 直接跑完整流程；`--dry-run` 只生成参数不发请求。
- 发码会给目标号码发**真实短信**，并消耗该 IP/会话的风控额度。
