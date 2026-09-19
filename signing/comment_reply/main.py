r"""main.py —— 抖音 Web 评论回复接口（/aweme/v1/web/comment/list/reply/）还原。

    GET https://www.douyin.com/aweme/v1/web/comment/list/reply/?item_id=<aweme_id>&comment_id=<cid>&cursor=0&count=20&<公共参数>&a_bogus=<签名>

⚠️ 已知边界（旧项目实测）：本端点被**端点级反爬**拦截 —— HTTP 200 但 `text/plain`、空 body；
   已证伪「登录态 / a_bogus / 参数」假设。程序会明确打印该结论。
   公共参数 / a_bogus / cookie / 请求 / --json-out 全在 `signing/_shared/`。

用法：
    python main.py --aweme-id 7626316866109066511 --comment-id 7673750309165007665
    python main.py ... --dry-run / --verbose / --json-out out.json
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
PATH_REPLY = "/aweme/v1/web/comment/list/reply/"


def main() -> int:
    parser = cli.build_parser("抖音 Web 评论回复接口还原（/aweme/v1/web/comment/list/reply/）", ROOT,
                                 default_abogus="nv8")
    parser.add_argument("--aweme-id", required=True, help="作品 id（作为 item_id）")
    parser.add_argument("--comment-id", required=True, help="父评论 cid")
    parser.add_argument("--cursor", default="0", help="翻页游标（默认 0）")
    parser.add_argument("--count", default="20", help="每页条数（默认 20）")
    args = parser.parse_args()
    cookie, verify = cli.prepare(args)

    params = C.build_params(item_id=args.aweme_id, comment_id=args.comment_id,
                            cursor=args.cursor, count=args.count,
                            cut_version="1", item_type="0")
    referer = f"https://www.douyin.com/video/{args.aweme_id}"
    try:
        signed = http.sign(PATH_REPLY, params, args.abogus_source)
    except SignerError as exc:
        print(f"签名失败：{exc}", file=sys.stderr)
        return 2

    logger.info("目标接口 : %s", PATH_REPLY)
    logger.info("item_id  : %s / comment_id : %s", args.aweme_id, args.comment_id)
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
        print("body（非 JSON）长度 :", len(resp.text))
        if resp.text:
            print(resp.text[:500])
        else:
            print("空 body —— 与旧项目结论一致：该端点有端点级反爬（text/plain + 空 body）")
    else:
        comments = parsed.get("comments") or []
        print("业务 status_code :", parsed.get("status_code"))
        print("本页条数         :", len(comments), "has_more =", parsed.get("has_more"))
    print("-" * 78)

    if args.json_out:
        http.write_json_out(args.json_out, PATH_REPLY, resp, parsed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
