r"""main.py —— 抖音 Web 视频详情接口（/aweme/v1/web/aweme/detail/）还原。

    GET https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=<id>&<公共参数>&a_bogus=<签名>

公共参数 / a_bogus / cookie / 请求 / --json-out 全在 `signing/_shared/`（唯一一份）；
本文件只有「接口路径 + 业务参数 + 打印摘要」。

用法：
    python main.py --aweme-id 7626316866109066511
    python main.py --aweme-id ... --dry-run / --verbose
    python main.py --aweme-id ... --cookie-file js_reverse_cache/private/session.json
    python main.py --aweme-id ... --json-out out.json      # 后端调度用
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # signing/

import requests                                     # noqa: E402

from _shared import cli, http                       # noqa: E402
from _shared import params as C                     # noqa: E402
from _shared.logger import logger                   # noqa: E402
from _shared.nv8 import Nv8Error, web_sign           # noqa: E402
from _shared.signer import SignerError              # noqa: E402

ROOT = Path(__file__).resolve().parent
PATH_DETAIL = "/aweme/v1/web/aweme/detail/"


def main() -> int:
    parser = cli.build_parser("抖音 Web 视频详情接口还原（/aweme/v1/web/aweme/detail/）", ROOT)
    parser.add_argument("--aweme-id", required=True, help="作品 id（15~20 位数字）")
    args = parser.parse_args()
    cookie, verify = cli.prepare(args)

    uifid = next((part[len("UIFID="):] for part in cookie.split("; ")
                  if part.startswith("UIFID=")), None)
    if not uifid:
        print("视频详情需要登录态中的 UIFID cookie", file=sys.stderr)
        return 2
    params = C.build_params(aweme_id=args.aweme_id, request_source="600",
                            origin_type="video_page", uifid=uifid)
    referer = f"https://www.douyin.com/video/{args.aweme_id}"
    try:
        signed, headers = web_sign(http.sign(PATH_DETAIL, params, args.abogus_source), uifid)
    except (SignerError, Nv8Error) as exc:
        print(f"签名失败：{exc}", file=sys.stderr)
        return 2

    logger.info("目标接口 : %s", PATH_DETAIL)
    logger.info("作品 id  : %s", args.aweme_id)
    http.dump_request(ROOT, signed)
    if args.verbose:
        logger.info("完整 URL :\n%s", signed)
    if args.dry_run:
        print("\n[dry-run] 未发送请求。去掉 --dry-run 即真正请求。")
        return 0

    try:
        resp, parsed = http.request(signed, cookie, referer, verify, headers)
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
        detail = parsed.get("aweme_detail") or {}
        author = detail.get("author") or {}
        stats = detail.get("statistics") or {}
        print("业务 status_code :", parsed.get("status_code"))
        print("作品 desc        :", (detail.get("desc") or "")[:80])
        print("作者             :", author.get("nickname"), "/", author.get("sec_uid"))
        print("点赞/评论/分享   :", stats.get("digg_count"), "/",
              stats.get("comment_count"), "/", stats.get("share_count"))
    print("-" * 78)

    if args.json_out:
        http.write_json_out(args.json_out, PATH_DETAIL, resp, parsed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
