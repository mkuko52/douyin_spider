"""logger.py —— 统一日志。

- 进度日志用 ``logger.info``。
- 响应数据用 :func:`log_json` / :func:`log_records`，默认有长度上限，避免刷屏。
- 绝不记录 cookie / token 等敏感值。

输出通道：默认 **stdout**（``DOUYIN_LOG_STREAM=stderr`` 可切回）。
原因：PowerShell / conhost 会把原生命令的 **stderr 渲染成红色**；采集器的日志是主要
输出，不该整片变红，也不该让 `python main.py > run.log` 丢掉日志。
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Iterable, TextIO


def _select_stream() -> TextIO:
    choice = os.environ.get("DOUYIN_LOG_STREAM", "stdout").strip().lower()
    if choice == "stderr":
        return sys.stderr
    return sys.stdout


def _configure_stream(stream: TextIO) -> None:
    """让日志流永远不会因无法编码的字符（如 emoji）而报错。

    - 输出到控制台（tty）：保留控制台原编码（zh-CN Windows 为 gbk，中文正常显示）。
    - 输出到管道/文件：使用 UTF-8，便于重定向与二次处理。
    - 强制指定：``DOUYIN_LOG_ENCODING=utf-8`` 或 ``gbk``。
    """
    encoding = os.environ.get("DOUYIN_LOG_ENCODING", "").strip()
    if not encoding:
        try:
            encoding = "" if stream.isatty() else "utf-8"
        except (AttributeError, ValueError, OSError):
            encoding = "utf-8"
    try:
        stream.reconfigure(encoding=encoding or None, errors="replace")
    except (AttributeError, ValueError, OSError):
        pass


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("douyin_spider")
    if logger.handlers:
        return logger
    stream = _select_stream()
    _configure_stream(stream)
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


logger = _build_logger()


def set_level(level: str | int) -> None:
    logger.setLevel(level)


def truncate(text: str, limit: int) -> str:
    if limit and len(text) > limit:
        return f"{text[:limit]}...<truncated {len(text) - limit} chars>"
    return text


def log_json(label: str, payload: Any, limit: int = 4000) -> None:
    """打印响应 JSON（有长度上限）。不要传入 cookie/token。"""
    try:
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        text = repr(payload)
    logger.info("%s\n%s", label, truncate(text, limit))


def log_records(label: str, records: Iterable[dict[str, Any]], limit: int = 50) -> None:
    """逐条打印还原后的记录（有数量上限）。"""
    records = list(records)
    logger.info("%s: %d record(s)", label, len(records))
    for index, record in enumerate(records[:limit], 1):
        logger.info("  [%d] %s", index, json.dumps(record, ensure_ascii=False))
    if len(records) > limit:
        logger.info("  ... <%d more>", len(records) - limit)
