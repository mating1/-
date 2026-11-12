# -*- coding: utf-8 -*-
"""xAgent 核心层。

分层约定（自下而上）：
    models / errors  → 纯数据结构与异常
    config           → 配置加载
    llm / tools      → 外部能力适配（模型、工具）
    session / agent  → 业务编排
    factory          → 依赖装配

core 层禁止 import 任何前端框架（textual / fastapi / tkinter ...），
所有对外输出都是事件对象（``core.events``）。
"""

from .agent import Agent
from .config import AppConfig, LLMConfig, load_config
from .errors import ConfigError, CoreError, LLMError, ToolError
from .events import (
    AgentEvent,
    AssistantDeltaEvent,
    AssistantMessageEvent,
    ErrorEvent,
    ToolCallFinishedEvent,
    ToolCallStartedEvent,
    TurnCompletedEvent,
    UserMessageEvent,
)
from .factory import build_agent, build_client, build_registry
from .models import Message, ToolCall, ToolExecution
from .session import Conversation
from .tools import FileSystemService, ToolRegistry

__all__ = [
    "Agent",
    "AgentEvent",
    "AppConfig",
    "AssistantDeltaEvent",
    "AssistantMessageEvent",
    "ConfigError",
    "Conversation",
    "CoreError",
    "ErrorEvent",
    "FileSystemService",
    "LLMConfig",
    "LLMError",
    "Message",
    "ToolCall",
    "ToolCallFinishedEvent",
    "ToolCallStartedEvent",
    "ToolError",
    "ToolExecution",
    "ToolRegistry",
    "TurnCompletedEvent",
    "UserMessageEvent",
    "build_agent",
    "build_client",
    "build_registry",
    "load_config",
]
