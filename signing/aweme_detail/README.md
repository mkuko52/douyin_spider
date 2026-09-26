# aweme_detail —— 抖音 Web 视频详情接口还原

    GET https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=<id>&uifid=<UIFID>&<公共参数>&a_bogus=<签名>&timestamp=<时间戳>&x-secsdk-web-signature=<动态签名>

## 结构

```text
aweme_detail/
  main.py                 # 只有「接口路径 + 业务参数 + 打印摘要」
  config.local.json       # cookie_file / verify_tls（私有，gitignored）
  requirements.txt        # requests + pyexecjs2
  tests/test_vectors.py   # URL 组装 + 本地 secsdk 签名（2 项，不发请求）
  output/                 # last_request.json
  js_reverse_cache/private/  # 本机登录态（凭证，gitignored）

../_shared/               # ★ 所有数据接口共用（唯一一份）
  params.py               # 公共参数 COMMON_PARAMS + build_url
  signer.py               # pyexecjs2 → node/mod.js（a_bogus）
  http.py                 # cookie 载入 / 请求头 / 发请求 / --json-out
  cli.py                  # 通用命令行开关
  logger.py
  node/mod.js             # a_bogus 签名器（与 send_code/sms_login 字节一致）
  tests/test_vectors.py   # 6 条 a_bogus 冻结向量
```

## 运行

```bash
# 离线测试：本接口 URL 组装（a_bogus 固定向量在 _shared）
python tests/test_vectors.py                              # 2/2
python ../_shared/tests/test_vectors.py                   # 3/3（6 条 a_bogus 冻结向量）

# 只组参数 + 签名，不发请求
python main.py --aweme-id 7626316866109066511 --cookie-file js_reverse_cache/private/session.json --dry-run --verbose

# 真实请求（需要登录态 cookie）
python main.py --aweme-id 7626316866109066511 \
  --cookie-file js_reverse_cache/private/session.json

# 后端调度用（见 android/AGENTS.md「接口契约」）
python main.py --aweme-id <id> --cookie-file <cookie> --json-out out.json
```

| 参数 | 说明 |
|---|---|
| `--aweme-id` | 作品 id（必填，15~20 位数字） |
| `--cookie-file` | 登录态 cookie；支持 storage_state / `{"jar":…}` / JSON / `k=v; k=v` |
| `--dry-run` | 只组参数与签名，不发请求 |
| `--verbose` | 打印完整 URL |
| `--verify-tls` | 严格校验 TLS（默认关闭） |
| `--check-login` | 请求前先确认会话是 www 登录态（否则退出码 3 + `NEED_LOGIN`，后端回 401） |
| `--json-out` | 把响应写成 JSON：`{path, status, content_type, headers, json}` |

## 边界

- **Node 只生成签名，`requests` 是唯一 HTTP 出口，不启动浏览器。**
  详情接口需要会话中的 `UIFID`、`a_bogus` 和本地 nv8/secsdk 生成的动态 `webSignUrl` 签名；
  缺少后者会收到 `403 Signature Not Found`。其他数据接口继续使用各自原有签名方式。
- `--dry-run` 也需提供含 `UIFID` 的 cookie，才能组出实际会发送的请求。
- 参数与契约来源：旧项目 `douyin_spider/utils/client.py` + 抓到的抖音前端源码
  `signing/send_code/js_reverse_cache/source/app_client-entry_*.js`。
