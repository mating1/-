# -*- coding: utf-8 -*-
"""fetchWeb 工具集。"""

from __future__ import annotations

from typing import List

from ..base import FunctionTool, Tool
from .service import FetchWebService

TOOL_FETCH_WEB = "fetchWeb"


def build_fetchweb_tools(service: FetchWebService = None) -> List[Tool]:
    service = service or FetchWebService()
    return [
        FunctionTool(
            name=TOOL_FETCH_WEB,
            description="获取指定网页的主要内容，通过本地 curl 取 HTML，再用 trafilatura 提取正文并转为 Markdown 返回给 LLM。会自动去除导航栏、广告、页脚等无关内容。",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要抓取的网页完整 URL"},
                },
                "required": ["url"],
            },
            func=lambda url: service.fetch_web(url),
        ),
    ]
