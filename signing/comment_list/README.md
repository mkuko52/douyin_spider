# comment_list —— 抖音 Web 评论列表接口还原

    GET https://www.douyin.com/aweme/v1/web/comment/list/?aweme_id=<id>&cursor=0&count=20&<公共参数>&a_bogus=<签名>

翻页：响应 `cursor` + `has_more`（`cursor` 取上一页返回值）。

## 结构

```text
comment_list/
  main.py                 # 只有「接口路径 + 业务参数 + 打印摘要」
  config.local.json       # cookie_file / verify_tls（gitignored）
  requirements.txt        # requests + pyexecjs2
  tests/test_vectors.py   # 本接口的 URL/参数组装（1 项）
  output/                 # last_request.json

../_shared/               # ★ 所有数据接口共用（唯一一份）：公共参数 / a_bogus / cookie / 请求
```

## 运行

```bash
python tests/test_vectors.py                     # 1/1
python ../_shared/tests/test_vectors.py          # 3/3（a_bogus 冻结向量）
python main.py --aweme-id 7626316866109066511
python main.py --aweme-id <id> --cursor 0 --count 20
python main.py --aweme-id <id> --cookie-file js_reverse_cache/private/session.json --json-out out.json
```

| 参数 | 说明 |
|---|---|
| `--aweme-id` | 作品 id（必填） |
| `--cursor` | 翻页游标（默认 0；取上一页返回值） |
| `--count` | 每页条数（默认 20） |
| `--cookie-file` / `--dry-run` / `--verbose` / `--verify-tls` / `--check-login` / `--json-out` | 同上 |

接口参数：`pc_img_format=webp&item_type=0&insert_ids=&whale_cut_token=&cut_version=1&rcFT=`。

## 验收

`status_code=0`，实测 `total=10399`，返回真实评论（见 `output/`）。
