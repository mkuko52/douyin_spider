# comment_reply —— 抖音 Web 评论回复接口还原

    GET https://www.douyin.com/aweme/v1/web/comment/list/reply/?item_id=<aweme_id>&comment_id=<cid>&cursor=0&count=20&<公共参数>&a_bogus=<签名>

## ✅ 已打通：唯一缺的是「真 bdms 的 a_bogus」

之前返回 `HTTP 200 + text/plain` 空 body，**不是登录态 / 不是 `bd-ticket-guard` 头 / 不是缺
`webid/msToken/fp`** —— 而是**本端点不认公开 `node/mod.js` 的 a_bogus，只认页面同款 bdms**。

实测（同一浏览器登录态、同一份 query）：

| a_bogus 来源 | 结果 |
|---|---|
| `node/mod.js`（公开移植版） | ❌ `text/plain` 空 body |
| **真 bdms（nv8）** | ✅ `application/json` `status_code=0` |

去掉全部 `bd-ticket-guard-*` 头仍然通过；`webid/uifid/verifyFp/fp/msToken` 也不是必要条件。
完整证据链见 `js_reverse_cache/env/reply_bdms_finding.md`。

**本项目默认 `--abogus-source nv8`**（真 bdms）；`--abogus-source modjs` 仅作对照（仍空 body）。
nv8 桥在 `../_shared/nv8.py`，复用 `sms_login/node/abogus_server.mjs`（不复制）。

### nv8 延迟：建议开常驻服务

| 取法 | 单次 a_bogus | 怎么跑 |
|---|---|---|
| **常驻服务（推荐）** | **~20ms** | `../_shared/start_nv8_service.bat`（:8789）|
| 本进程起 Node（回落） | ~5-6s | 什么都不用做 |

实测：走服务时 `comment_reply` 端到端 **1.16s**（含 `--check-login`）；不开服务则每个请求多 ~5s。
服务地址可用 `NV8_SERVICE_URL` 覆盖（默认 `http://127.0.0.1:8789`）。

## 运行

```bash
python tests/test_vectors.py                     # 1/1（本接口 URL 组装）
python ../_shared/tests/test_vectors.py          # 3/3（a_bogus 冻结向量）
python main.py --aweme-id 7626316866109066511 --comment-id 7673750309165007665
python main.py ... --dry-run / --verbose / --json-out out.json
```

| 参数 | 说明 |
|---|---|
| `--aweme-id` | 作品 id（作为 `item_id`，必填） |
| `--comment-id` | 父评论 cid（必填） |
| `--cursor` / `--count` | 翻页游标 / 每页条数 |
| `--cookie-file` / `--dry-run` / `--verbose` / `--verify-tls` / `--check-login` / `--json-out` | 同上 |
| `--abogus-source` | `modjs`（公开移植版，对照用）/ **`nv8`（默认，真 bdms，唯一能过）** |

接口参数：`cut_version=1&item_type=0`。

## 验收

`status_code=0` / `application/json`（本项目默认 nv8）—— 实测返回真实回复（`n=3 has_more=1`）。
