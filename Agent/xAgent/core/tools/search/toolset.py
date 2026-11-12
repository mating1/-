# -*- coding: utf-8 -*-
"""searchTool 工具集。"""

from __future__ import annotations

from typing import List

from ..base import FunctionTool, Tool
from .service import SearchService

TOOL_SEARCH = "searchWeb"


def build_search_tools(service: SearchService = None) -> List[Tool]:
    service = service or SearchService()
    return [
        FunctionTool(
            name=TOOL_SEARCH,
            description="调用外部搜索服务 API 检索网络资料，返回标题、链接与摘要；未配置搜索后端时会返回明确的缺配置提示。",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词或问题"},
                },
                "required": ["query"],
            },
            func=lambda query: service.search(query),
        ),
    ]
