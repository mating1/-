# -*- coding: utf-8 -*-
"""recallContext 工具集装配。"""

from __future__ import annotations

from typing import List

from ..base import FunctionTool, Tool
from .service import ContextSearchService


def build_context_tools(
    project_root: str = ".",
    archive_dirname: str = ".agents/context",
    limit: int = 8,
    snippet: int = 240,
) -> List[Tool]:
    """注册 recallContext 工具，用于检索历史上下文归档。"""
    service = ContextSearchService(project_root, archive_dirname, limit, snippet)

    return [
        FunctionTool(
            name="recallContext",
            description=(
                "检索此前被压缩归档的原始上下文。当压缩摘要缺少某些历史细节时调用。"
                "id 可选：指定归档编号；不填则在所有历史归档中检索。text 必需：要查找的关键词或文本。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "可选，指定要检索的上下文归档编号，例如 20261022-153000。",
                    },
                    "text": {
                        "type": "string",
                        "description": "必需，需要查找的关键词或文本内容。",
                    },
                },
                "required": ["text"],
            },
            func=lambda id="", text="": service.recall(id=id, text=text),
        )
    ]
