# aweme_feed —— 抖音 Web 视频列表（推荐页 tab feed）接口还原

    GET https://www.douyin.com/aweme/v1/web/tab/feed/?count=10&refresh_index=1&tab=&type=0&<公共参数>&a_bogus=<签名>

翻页：`refresh_index` 递增；响应 `aweme_list` 是视频列表（含 aweme_id / desc / author / statistics / video）。

## 运行

```bash
python tests/test_vectors.py                     # 1/1（本接口 URL 组装）
python ../_shared/tests/test_vectors.py          # 3/3（a_bogus 冻结向量）
python main.py
python main.py --count 10 --refresh-index 1
python main.py --cookie-file js_reverse_cache/private/session.json --json-out out.json
```

| 参数 | 说明 |
|---|---|
| `--count` | 每页条数（默认 10） |
| `--refresh-index` | 翻页序号（默认 1，递增） |
| `--tab` / `--type` | tab 标识 / 列表类型（默认空 / 0） |
| `--cookie-file` / `--dry-run` / `--verbose` / `--verify-tls` / `--check-login` / `--json-out` | 同上 |

## 验收

`status_code=0`，返回真实 `aweme_list`（本轮实测本页 2 条、`has_more=1`）。
