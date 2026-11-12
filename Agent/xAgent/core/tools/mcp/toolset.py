# -*- coding: utf-8 -*-
"""MCP 工具集：把发现的 MCP Server 工具包装成 xAgent 本地 Tool。"""

from __future__ import annotations

from typing import List

from ..base import FunctionTool, Tool
from .service import MCPBridge


def make_mcp_tools(bridge: MCPBridge) -> List[Tool]:
    """把已注册到 bridge 的 MCP 工具包装成 xAgent Tool（不触发连接）。

    供异步加载流程使用：TUI 先启动，再在后台线程连接 MCP 后调用本函数，
    把工具动态注册进 registry。
    """
    tools: List[Tool] = []
    for name, meta in bridge._tool_meta.items():  # noqa: SLF001
        tools.append(
            FunctionTool(
                name=name,
                description=meta["description"],
                parameters=meta["parameters"],
                func=lambda _name=name, **kwargs: bridge.call(_name, kwargs or {}),
            )
        )
    return tools


def build_mcp_tools(bridge: MCPBridge) -> List[Tool]:
    """连接 MCP Server 并返回其工具（同步阻塞版本，保留兼容）。

    - 无 .mcp.json 或无可连接 Server 时返回空列表。
    - 多个 Server 时暴露名带前缀 <server>_<tool> 以避免冲突。
    """
    if not bridge.available:
        return []
    bridge.start()
    return make_mcp_tools(bridge)


__all__ = ["MCPBridge", "build_mcp_tools", "make_mcp_tools"]
