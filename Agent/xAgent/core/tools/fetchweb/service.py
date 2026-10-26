# -*- coding: utf-8 -*-
"""网页抓取服务：用 curl 取 HTML，trafilatura 抽正文转 Markdown。"""

from __future__ import annotations

import subprocess
import sys

import trafilatura


class FetchWebService:
    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout

    def fetch_web(self, url: str) -> str:
        if not url:
            return "url 不能为空"
        try:
            proc = subprocess.run(
                [
                    "curl",
                    "-sSL",
                    "--max-time", str(self.timeout),
                    "-A", "Mozilla/5.0",
                    url,
                ],
                capture_output=True,
                timeout=self.timeout + 5,
            )
        except FileNotFoundError:
            return "未找到 curl 命令，请确认系统已安装 curl"
        except subprocess.TimeoutExpired:
            return "请求超时：%s" % url
        except OSError as exc:
            return "调用 curl 失败：%s" % exc

        if proc.returncode != 0:
            err = self._decode(proc.stderr).strip()
            return "curl 返回错误（exit=%s）：%s" % (proc.returncode, err or self._decode(proc.stdout)[:300])

        html = self._decode(proc.stdout)
        if not html:
            return "网页内容为空：%s" % url

        try:
            markdown = trafilatura.extract(
                html,
                output_format="markdown",
                url=url,
                include_links=True,
                include_images=False,
                include_tables=True,
                favor_precision=True,
            )
        except Exception as exc:  # noqa: BLE001
            return "HTML 解析失败：%s" % exc

        if not markdown or not markdown.strip():
            return "未能从该网页提取到正文：%s" % url

        return "原始 URL：%s\n\n%s" % (url, markdown)

    @staticmethod
    def _decode(raw: bytes) -> str:
        for enc in ("utf-8", "gbk", sys.getfilesystemencoding()):
            try:
                return raw.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return raw.decode("utf-8", errors="replace")
