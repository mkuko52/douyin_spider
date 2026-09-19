r"""main.py —— 抖音 Web 视频列表（推荐页 tab feed）接口还原。

    GET https://www.douyin.com/aweme/v1/web/tab/feed/?count=10&refresh_index=1&tab=&type=0&<公共参数>&a_bogus=<签名>

翻页：`refresh_index` 递增；响应 `aweme_list` 是视频列表。
公共参数 / a_bogus / cookie / 请求 / --json-out 全在 `signing/_shared/`。

用法：
    python main.py
    python main.py --count 10 --refresh-index 1
    python main.py --dry-run / --verbose / --json-out out.json
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
PATH_FEED = "/aweme/v1/web/tab/feed/"


def main() -> int:
    parser = cli.build_parser("抖音 Web 视频列表接口还原（/aweme/v1/web/tab/feed/）", ROOT)
    parser.add_argument("--count", default="10", help="每页条数（默认 10）")
    parser.add_argument("--refresh-index", default="1", help="翻页序号（默认 1，递增）")
    parser.add_argument("--tab", default="", help="tab 标识（默认空 = 推荐）")
    parser.add_argument("--type", default="0", help="列表类型（默认 0）")
    args = parser.parse_args()
    cookie, verify = cli.prepare(args)

    params = C.build_params(count=args.count, refresh_index=args.refresh_index,
                            tab=args.tab, type=args.type)
    try:
        signed = http.sign(PATH_FEED, params, args.abogus_source)
    except SignerError as exc:
        print(f"签名失败：{exc}", file=sys.stderr)
        return 2

    logger.info("目标接口 : %s", PATH_FEED)
    logger.info("分页     : count=%s refresh_index=%s", args.count, args.refresh_index)
    http.dump_request(ROOT, signed)
    if args.verbose:
        logger.info("完整 URL :\n%s", signed)
    if args.dry_run:
        print("\n[dry-run] 未发送请求。去掉 --dry-run 即真正请求。")
        return 0

    try:
        resp, parsed = http.request(signed, cookie, "https://www.douyin.com/", verify)
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
        items = parsed.get("aweme_list") or []
        print("业务 status_code :", parsed.get("status_code"))
        print("本页条数         :", len(items), "has_more =", parsed.get("has_more"))
        if items:
            first = items[0]
            print("首条作品         :", first.get("aweme_id"),
                  "/", (first.get("desc") or "")[:40],
                  "/ 作者", (first.get("author") or {}).get("nickname"))
    print("-" * 78)

    if args.json_out:
        http.write_json_out(args.json_out, PATH_FEED, resp, parsed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
