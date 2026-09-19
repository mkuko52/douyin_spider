# user_profile —— 抖音 Web 用户信息接口还原

    GET https://www.douyin.com/aweme/v1/web/user/profile/other/?sec_user_id=<sec_uid>&publish_video_strategy_type=2&<公共参数>&a_bogus=<签名>

`sec_user_id` 从视频/评论响应里的 `author.sec_uid` 取（或分享主页链接里的 `sec_uid`）。

## 运行

```bash
python tests/test_vectors.py                     # 1/1（本接口 URL 组装）
python ../_shared/tests/test_vectors.py          # 3/3（a_bogus 冻结向量）
python main.py --sec-user-id MS4wLjABAAAA...
python main.py --sec-user-id ... --cookie-file js_reverse_cache/private/session.json --json-out out.json
```

| 参数 | 说明 |
|---|---|
| `--sec-user-id` | 用户 sec_uid（`MS4wLjABAAAA...`，必填） |
| `--cookie-file` / `--dry-run` / `--verbose` / `--verify-tls` / `--check-login` / `--json-out` | 同上 |

## 验收

`status_code=0`，返回 `user`（昵称 / 抖音号 / 关注·粉丝·获赞 / 作品数 / 签名）。
本轮实测（傲安）：粉丝 1774701、作品 1821。

> 注：`user/profile/other` 是**公开**接口，匿名 cookie 亦可返回；
> 若要查「自己」（`user/profile/self`）才需要登录态。
