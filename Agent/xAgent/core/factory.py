# -*- coding: utf-8 -*-
"""应用装配工厂。

各前端（tui / web / desktop / mobile）都通过这里拿到同一个 Agent 实例，
保证"核心能力一致、前端只负责展示"。

MCP Server 不在这里同步连接：只创建桥对象，由 TUI 在后台线程调用
``agent.load_mcp()`` 异步加载并动态补注册工具，从而做到"先进入界面、再刷新"。
"""

from __future__ import annotations

from typing import Optional

from .agent import Agent
from .config import AppConfig
from .context import ContextManager
from .llm.client import LLMClient
from .session import Conversation
from .session_store import SessionStore
from .skills import build_skills_prompt, discover_skills
from .tracing import configure as configure_tracing
from .tools.context import build_context_tools
from .tools.fileops import FileSystemService, build_file_tools
from .tools.fetchweb import build_fetchweb_tools
from .tools.mcp import MCPBridge
from .tools.registry import ToolRegistry
from .tools.runcli import run_cli_tool
from .tools.search import build_search_tools
from .tools.skills import SkillService, build_skill_tools
from .tools.systime import build_systime_tools


def build_registry(
    service: Optional[FileSystemService] = None,
    project_root: Optional[str] = None,
    config: Optional[AppConfig] = None,
) -> ToolRegistry:
    """装配默认工具集（不含 MCP，MCP 由异步加载补注册）。

    project_root 为当前项目（workspace）目录：用于技能发现、上下文归档检索。
    """
    root = project_root or "."
    archive_dirname = config.archive_dirname if config else ".agents/context"
    recall_limit = config.recall_limit if config else 8
    recall_snippet = config.recall_snippet if config else 240
    tools = (
        build_file_tools(service or FileSystemService(root=root, strict_root=True))
        + build_systime_tools()
        + build_fetchweb_tools()
        + build_search_tools()
        + run_cli_tool()
        + build_skill_tools(SkillService(root))
        + build_context_tools(root, archive_dirname, recall_limit, recall_snippet)
    )
    return ToolRegistry(tools)


def build_client(config: AppConfig, registry: ToolRegistry) -> LLMClient:
    """装配大模型客户端，并把工具 schema 注入进去。"""
    return LLMClient(config.llm, tool_schemas=registry.schemas())


def build_agent(config: AppConfig, registry: Optional[ToolRegistry] = None) -> Agent:
    """按配置装配一个可用的 Agent，初始化阶段发现并注册 Skill。"""
    configure_tracing(config.workspace)
    registry = registry or build_registry(project_root=config.workspace, config=config)
    client = build_client(config, registry)
    skills_prompt = build_skills_prompt(discover_skills(config.workspace))
    system_prompt = "\n\n".join(
        part for part in (config.system_prompt, skills_prompt) if part
    )
    conversation = Conversation(system_prompt=system_prompt)
    context_manager = ContextManager(
        workspace=config.workspace,
        llm=config.llm,
        window_tokens=config.context_window,
        threshold=config.context_threshold,
        window_is_default=config.context_window_is_default,
        archive_dirname=config.archive_dirname,
        recall_limit=config.recall_limit,
        recall_snippet=config.recall_snippet,
    )
    session_store = SessionStore(config.workspace, config.session_dirname)
    bridge = MCPBridge(
        config.workspace,
        connect_timeout=config.mcp_connect_timeout,
        call_timeout=config.mcp_call_timeout,
    )
    return Agent(
        client=client,
        registry=registry,
        conversation=conversation,
        max_iterations=config.max_iterations,
        system_prompt=system_prompt,
        context_manager=context_manager,
        mcp_bridge=bridge,
        session_store=session_store,
        agents_file=config.agents_filename,
        workspace=config.workspace,
    )
