r"""main.py —— 抖音 Web 关键词搜索接口（/aweme/v1/web/search/item/）还原。

    GET https://www.douyin.com/aweme/v1/web/search/item/?keyword=<词>&offset=0&count=20&<公共参数>&a_bogus=<签名>

⚠️ 该接口**需要 login.douyin.com 之外的 www.douyin.com 登录态**：未登录/非 www 登录
   返回 `status_code=2483 请先登录，再继续搜索吧`。见 README「已知边界」。
   公共参数 / a_bogus / cookie / 请求 / --json-out 全在 `signing/_shared/`。

用法：
    python main.py --keyword minecraft --offset 0 --count 20
    python main.py --keyword ... --dry-run / --verbose / --json-out out.json
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # signing/

import requests                                     # noqa: E402

from _shared import cli, http                       # noqa: E402
from _shared import params as C                     # noqa: E402
from _shared.logger import logger                   # noqa: E402
from _shared.signer import SignerError              # noqa: E402

ROOT = Path(__file__).resolve().parent
PATH_SEARCH = "/aweme/v1/web/search/item/"


def main() -> int:
    parser = cli.build_parser("抖音 Web 关键词搜索接口还原（/aweme/v1/web/search/item/）", ROOT)
    parser.add_argument("--keyword", required=True, help="搜索关键词")
    parser.add_argument("--offset", default="0", help="偏移（默认 0，翻页递增）")
    parser.add_argument("--count", default="20", help="每页条数（默认 20）")
    args = parser.parse_args()
    cookie, verify = cli.prepare(args)

    params = C.build_params(
        keyword=args.keyword, offset=args.offset, count=args.count,
        search_channel="aweme_video", search_source="tab_search",
        query_correct_type="1", is_filter_search="0", sort_type="0",
        publish_time="0", filter_duration="0", source="normal_search", search_id="",
    )
    referer = f"https://www.douyin.com/search/{quote(args.keyword)}"
    try:
        signed = http.sign(PATH_SEARCH, params, args.abogus_source)
    except SignerError as exc:
        print(f"签名失败：{exc}", file=sys.stderr)
        return 2

    logger.info("目标接口 : %s", PATH_SEARCH)
    logger.info("关键词   : %s (offset=%s count=%s)", args.keyword, args.offset, args.count)
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
        items = parsed.get("aweme_list") or parsed.get("data") or []
        print("业务 status_code :", parsed.get("status_code"),
              "(2483 = 未登录，需先登录)")
        print("本页条数         :", len(items) if isinstance(items, list) else "-",
              "has_more =", parsed.get("has_more"))
        if isinstance(items, list) and items:
            first = items[0]
            aweme = first.get("aweme_info") or first.get("aweme_detail") or first
            print("首条作品         :", aweme.get("aweme_id"),
                  "/", (aweme.get("desc") or "")[:40],
                  "/ 作者", (aweme.get("author") or {}).get("nickname"))
    print("-" * 78)

    if args.json_out:
        http.write_json_out(args.json_out, PATH_SEARCH, resp, parsed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
