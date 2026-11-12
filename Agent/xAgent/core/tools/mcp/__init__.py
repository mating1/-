# -*- coding: utf-8 -*-
"""MCP Client：让 xAgent 连接外部 MCP Server 并调用其工具。"""

from .service import MCPBridge
from .toolset import build_mcp_tools

__all__ = ["MCPBridge", "build_mcp_tools"]
