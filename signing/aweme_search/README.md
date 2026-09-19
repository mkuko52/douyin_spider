# aweme_search —— 抖音 Web 关键词搜索接口还原

    GET https://www.douyin.com/aweme/v1/web/search/item/?keyword=<词>&offset=0&count=20&<公共参数>&a_bogus=<签名>

翻页：`offset` 递增；响应 `aweme_list[].aweme_info` 是作品详情。

## ⚠️ 需要真正登录 `www.douyin.com` 的会话

本接口是**登录门控**：无登录态（或会话过期）返回 `status_code=2483 请先登录，再继续搜索吧`。

实测（本轮）：

| cookie | `/aweme/v1/web/notice/count/`（登录判定） | 本接口 |
|---|---|---|
| 无 cookie | — | `2483` |
| `sms_login_session.json`（已过期） | `8 用户未登录` | `2483` |
| **`async_session.json`（活的 www 登录）** | **`0`** | **`0`，返回真实作品** ✅ |

- 登录判定接口：`GET /aweme/v1/web/notice/count/`（或 `/user/profile/self/`）→ `status_code=8` 即未登录，`0` 即已登录。
- **同一账号再次登录会让旧会话失效**：所以要多份会话时，只有最近一次登录的那份是活的
  （`sms_login_session.json` / `nv8_session.json` 现在都是 `account_info error_code=13 会话过期`）。
- 补 `webid` / `msToken` / `fp` 对本接口没有帮助（那是设备参数，不是登录态）。

结论：本接口**确实需要前端携带登录态**（App 登录 → 后端缓存会话 → `--cookie-file`），
登录态是获的，live 已打通。

## 运行

```bash
python tests/test_vectors.py                     # 1/1（本接口 URL 组装）
python ../_shared/tests/test_vectors.py          # 3/3（a_bogus 冻结向量）
python main.py --keyword minecraft --count 10
python main.py --keyword "我的世界" --offset 0 --count 20
python main.py --keyword ... --cookie-file js_reverse_cache/private/session.json --json-out out.json
```

| 参数 | 说明 |
|---|---|
| `--keyword` | 搜索关键词（必填） |
| `--offset` / `--count` | 偏移（默认 0）/ 每页条数（默认 20） |
| `--cookie-file` / `--dry-run` / `--verbose` / `--verify-tls` / `--check-login` / `--json-out` | 同上 |

接口参数：`search_channel=aweme_video&search_source=tab_search&query_correct_type=1&is_filter_search=0&sort_type=0&publish_time=0&filter_duration=0&source=normal_search&search_id=`。
