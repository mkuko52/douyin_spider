r"""main.py —— 抖音 Web 评论列表接口（/aweme/v1/web/comment/list/）还原。

    GET https://www.douyin.com/aweme/v1/web/comment/list/?aweme_id=<id>&cursor=0&count=20&<公共参数>&a_bogus=<签名>

翻页：响应 `cursor` + `has_more`（`cursor` 取上一页返回值）。
公共参数 / a_bogus / cookie / 请求 / --json-out 全在 `signing/_shared/`。

用法：
    python main.py --aweme-id 7626316866109066511 --count 20 --cursor 0
    python main.py --aweme-id ... --dry-run / --verbose / --json-out out.json
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
PATH_COMMENT = "/aweme/v1/web/comment/list/"


def main() -> int:
    parser = cli.build_parser("抖音 Web 评论列表接口还原（/aweme/v1/web/comment/list/）", ROOT)
    parser.add_argument("--aweme-id", required=True, help="作品 id（15~20 位数字）")
    parser.add_argument("--cursor", default="0", help="翻页游标（默认 0；取上一页返回值）")
    parser.add_argument("--count", default="20", help="每页条数（默认 20）")
    args = parser.parse_args()
    cookie, verify = cli.prepare(args)

    params = C.build_params(
        aweme_id=args.aweme_id, cursor=args.cursor, count=args.count,
        pc_img_format="webp", item_type="0", insert_ids="",
        whale_cut_token="", cut_version="1", rcFT="",
    )
    referer = f"https://www.douyin.com/video/{args.aweme_id}"
    try:
        signed = http.sign(PATH_COMMENT, params, args.abogus_source)
    except SignerError as exc:
        print(f"签名失败：{exc}", file=sys.stderr)
        return 2

    logger.info("目标接口 : %s", PATH_COMMENT)
    logger.info("作品 id  : %s (cursor=%s count=%s)", args.aweme_id, args.cursor, args.count)
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
        comments = parsed.get("comments") or []
        print("业务 status_code :", parsed.get("status_code"))
        print("评论总数         :", parsed.get("total"))
        print("本页条数         :", len(comments), "has_more =", parsed.get("has_more"))
        print("下一页 cursor    :", parsed.get("cursor"))
        if comments:
            first = comments[0]
            print("首条评论         :", (first.get("text") or "")[:60],
                  "/ 赞", first.get("digg_count"),
                  "/ 作者", (first.get("user") or {}).get("nickname"))
    print("-" * 78)

    if args.json_out:
        http.write_json_out(args.json_out, PATH_COMMENT, resp, parsed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
