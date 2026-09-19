# _shared —— 数据接口（`/aweme/v1/web/*`）共用参数层

**唯一一份**。`signing/` 下每个数据接口项目（`aweme_detail` / `comment_list` /
`comment_reply` / `aweme_feed` / `user_profile` / `aweme_search`）都从这里取参数与签名，
不再各自复制 `mod.js` / 公共参数。

```text
_shared/
├── __init__.py
├── params.py           # COMMON_PARAMS + build_params / build_url（公共参数）
├── node.py             # 项目自带 node 的解析（DOUYIN_NODE → send_code/runtime/node_local → PATH）
├── signer.py           # pyexecjs2 → node/mod.js（a_bogus，快）
├── nv8.py              # 真 bdms a_bogus（replies 必须用；复用 sms_login/node/abogus_server.mjs）
│                       # 优先走常驻服务，服务没开则回落本进程起 Node
├── nv8_service.py      # ★常驻 nv8 工件服务（HTTP :8789）：Node/bdms 只启一次
├── start_nv8_service.bat / .sh   # 启常驻服务（Windows / Linux·macOS）
├── http.py             # load_cookie_file / build_headers / sign / request / write_json_out
│                       # + 登录态检查：PATH_LOGIN_CHECK / is_logged_in / assert_login
├── cli.py              # 通用命令行开关（--cookie-file/--dry-run/--verbose/--verify-tls/--check-login/--config/--json-out）
├── logger.py           # 统一日志（stdout）
├── node/mod.js         # a_bogus 签名器（与 send_code/sms_login 字节一致）
└── tests/test_vectors.py   # 6 条 a_bogus 冻结向量 + build_url/sign_url
```

## 各数据接口怎么用

```python
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # signing/

from _shared import cli, http
from _shared import params as C
from _shared.logger import logger
from _shared.signer import SignerError

ROOT = Path(__file__).resolve().parent
PATH = "/aweme/v1/web/..."          # ← 只有「路径 + 业务参数 + 打印」是本项目独有的

def main() -> int:
    parser = cli.build_parser("...", ROOT)
    parser.add_argument("--xxx", ...)
    args = parser.parse_args()
    cookie, verify = cli.prepare(args)            # --check-login 时先确认 www 登录态
    params = C.build_params(xxx=args.xxx)
    signed = http.sign(PATH, params)              # 组 URL + a_bogus
    http.dump_request(ROOT, signed)               # output/last_request.json
    resp, parsed = http.request(signed, cookie, referer, verify)
    if args.json_out:
        http.write_json_out(args.json_out, PATH, resp, parsed)
```

## 边界

- **a_bogus 只有这一份**（`node/mod.js`）。数据接口（`/aweme/v1/web/*`）只需 a_bogus，
  **不需要浏览器 / dtrait**；登录类接口（`/passport/web/*`）才需要，它们**不共用**本包。
- **Node 不依赖系统 PATH**：`node.py` 优先用 `send_code/runtime/node_local/node.exe`
  （`execjs` 靠 PATH 找 node → `signer.py` 先把自带目录插到 PATH 最前；`nv8.py` 直接拿路径）。
  可用 `DOUYIN_NODE` 指定；自带的没有才回落 PATH。
- 登录类项目（`send_code` / `sms_login`）参数完全不同（enc/sign/qs/aid-sign/dtrait），
  仍是各自独立的 project-root，不引用 `_shared`。

## a_bogus 来源（`--abogus-source`）

| 来源 | 实现 | 特点 | 哪些接口能用 |
|---|---|---|---|
| `modjs`（默认） | 公开移植版 `node/mod.js`（pyexecjs2） | 快（~0.5s） | detail / comments / feed / user / search |
| `nv8` | 页面同款 **bdms** 字节码（nv8 补环境） | 见下 | 以上全部 + **`replies`** |

`/aweme/v1/web/comment/list/reply/` 是唯一“挑签名”的：mod.js 的 a_bogus 它不认，只认真 bdms。
证据：`signing/comment_reply/js_reverse_cache/env/reply_bdms_finding.md`。

### nv8 的两种取法（延迟差 100 倍）

`nv8.py` **不复制**任何工件：直接跑 `sms_login/node/abogus_server.mjs`（登录项目是 bdms 工件的唯一持有者）。
依赖 `NV8_SRC`（默认 `D:/develop_software/nv8/src/index.js`）。

| 取法 | 延迟 | 怎么跑 |
|---|---|---|
| **常驻服务（推荐）** | **~20ms** | `start_nv8_service.bat` / `python -m _shared.nv8_service`（`127.0.0.1:8789`）|
| 本进程起 Node（回落） | ~5-6s | 什么都不用做：服务没开时自动回落 |

常驻服务地址可用 `NV8_SERVICE_URL` 覆盖。接口：`GET /health`、`POST /abogus`。
实测：单次 a_bogus 走服务 **17-32ms**；`comment_reply` 端到端 **1.16s**（含 `--check-login`）。

## 登录态检查（`--check-login`）

数据接口分两档：

- **公开**（`detail` / `comments` / `feed` / `user`）：只需一个带 `ttwid` 的**会话**（匿名会被
  `text/plain` 空 body 挡回）。
- **登录门控**：`search`（无登录态 → `2483`）。
- `replies`：不卡登录，但卡 **a_bogus 来源**（必须 `nv8`，见上）。

后端每个数据路由都会传 `--check-login`：项目先 `GET /aweme/v1/web/notice/count/`，
`status_code != 0`（`8` = 未登录/会话过期）就打 `NEED_LOGIN: …` 到 stderr 并以**退出码 3** 结束。
后端的 `_run_cli` 把它抬成 `DouyinAuthError` → **HTTP 401 请重新登录**，
而不是让 App 看到 `2483` / 空 body 去猜。

```bash
# 手动检查一份会话：
python aweme_detail/main.py --aweme-id <id> --cookie-file <ck> --check-login
# 已登录 -> 正常请求；未登录 -> stderr: NEED_LOGIN: …，退出码 3
```

## 运行

```bash
python _shared/tests/test_vectors.py     # 4/4（6 条 a_bogus 冻结向量 + 登录判定）
```
