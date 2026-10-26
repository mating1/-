# -*- coding: utf-8 -*-
"""应用装配工厂。

各前端（tui / web / desktop / mobile）都通过这里拿到同一个 Agent 实例，
保证"核心能力一致、前端只负责展示"。
"""

from __future__ import annotations

from typing import Optional

from .agent import Agent
from .config import AppConfig
from .llm.client import LLMClient
from .session import Conversation
from .tools.fileops import FileSystemService, build_file_tools
from .tools.fetchweb import build_fetchweb_tools
from .tools.registry import ToolRegistry
from .tools.runcli import run_cli_tool
from .tools.systime import build_systime_tools


def build_registry(service: Optional[FileSystemService] = None) -> ToolRegistry:
    """装配默认工具集。"""
    tools = (
        build_file_tools(service or FileSystemService())
        + build_systime_tools()
        + build_fetchweb_tools()
        + run_cli_tool()
    )
    return ToolRegistry(tools)


def build_client(config: AppConfig, registry: ToolRegistry) -> LLMClient:
    """装配大模型客户端，并把工具 schema 注入进去。"""
    return LLMClient(config.llm, tool_schemas=registry.schemas())


def build_agent(config: AppConfig, registry: Optional[ToolRegistry] = None) -> Agent:
    """按配置装配一个可用的 Agent。"""
    registry = registry or build_registry()
    client = build_client(config, registry)
    conversation = Conversation(system_prompt=config.system_prompt)
    return Agent(
        client=client,
        registry=registry,
        conversation=conversation,
        max_iterations=config.max_iterations,
        system_prompt=config.system_prompt,
    )
