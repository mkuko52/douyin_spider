r"""main.py —— 抖音 Web 用户信息接口（/aweme/v1/web/user/profile/other/）还原。

    GET https://www.douyin.com/aweme/v1/web/user/profile/other/?sec_user_id=<sec_uid>&publish_video_strategy_type=2&<公共参数>&a_bogus=<签名>

`sec_user_id` 从视频/评论响应里的 `author.sec_uid` 取（或分享主页链接里的 `sec_uid`）。
公共参数 / a_bogus / cookie / 请求 / --json-out 全在 `signing/_shared/`。

用法：
    python main.py --sec-user-id MS4wLjABAAAA...
    python main.py --sec-user-id ... --dry-run / --verbose / --json-out out.json
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # signing/

import requests                                     # noqa: E402

from _shared import cli, http                       # noqa: E402
from _shared import params as C                     # noqa: E402
from _shared.logger import logger                   # noqa: E402
from _shared.signer import SignerError              # noqa: E402

ROOT = Path(__file__).resolve().parent
PATH_PROFILE = "/aweme/v1/web/user/profile/other/"


def main() -> int:
    parser = cli.build_parser("抖音 Web 用户信息接口还原（/aweme/v1/web/user/profile/other/）", ROOT)
    parser.add_argument("--sec-user-id", required=True, help="用户 sec_uid（MS4wLjABAAAA...）")
    args = parser.parse_args()
    cookie, verify = cli.prepare(args)

    params = C.build_params(sec_user_id=args.sec_user_id, publish_video_strategy_type="2")
    referer = f"https://www.douyin.com/user/{args.sec_user_id}"
    try:
        signed = http.sign(PATH_PROFILE, params, args.abogus_source)
    except SignerError as exc:
        print(f"签名失败：{exc}", file=sys.stderr)
        return 2

    logger.info("目标接口 : %s", PATH_PROFILE)
    logger.info("sec_uid  : %s…", args.sec_user_id[:32])
    http.dump_request(ROOT, signed)
    if args.verbose:
        logger.info("完整 URL :\n%s", signed)
    if args.dry_run:
        print("\n[dry-run] 未发送请求。去掉 --dry-run 即真正请求。")
        return 0

    try:
        resp, parsed = http.request(signed, cookie, referer, verify)
    except requests.RequestException as exc:
        print(f"请求失败：{exc}", file=sys.stderr)
        return 2

    print("\n" + "-" * 78)
    print("HTTP 状态码 :", resp.status_code)
    print("Content-Type:", resp.headers.get("content-type", ""))
    print("-" * 78)
    if parsed is None:
        print(f"body（非 JSON）: {resp.text[:300] or '空'}")
    else:
        user = parsed.get("user") or {}
        print("业务 status_code :", parsed.get("status_code"))
        print("昵称             :", user.get("nickname"))
        print("抖音号           :", user.get("unique_id") or user.get("short_id"))
        print("关注/粉丝/获赞   :", user.get("following_count"), "/",
              user.get("follower_count"), "/", user.get("total_favorited"))
        print("作品数           :", user.get("aweme_count"))
        print("签名             :", (user.get("signature") or "")[:60])
    print("-" * 78)

    if args.json_out:
        http.write_json_out(args.json_out, PATH_PROFILE, resp, parsed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
