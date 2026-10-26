# -*- coding: utf-8 -*-
"""Agent 运行过程中对外抛出的事件对象。

core 层只产生事件，不做任何渲染；不同前端（TUI / Web / Desktop）
各自消费同一套事件，从而做到"一次实现，多端复用"。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from .models import ToolCall, ToolExecution


@dataclass
class AgentEvent:
    """事件基类，``kind`` 用于日志与调试。"""

    kind: ClassVar[str] = "event"


@dataclass
class UserMessageEvent(AgentEvent):
    """用户输入已被接受。"""

    kind: ClassVar[str] = "user_message"
    text: str = ""


@dataclass
class AssistantDeltaEvent(AgentEvent):
    """助手回复的流式增量片段。"""

    kind: ClassVar[str] = "assistant_delta"
    text: str = ""


@dataclass
class AssistantMessageEvent(AgentEvent):
    """助手回复的完整内容（本轮没有再触发工具调用时发出）。"""

    kind: ClassVar[str] = "assistant_message"
    text: str = ""


@dataclass
class ToolCallStartedEvent(AgentEvent):
    """即将执行一次工具调用。"""

    kind: ClassVar[str] = "tool_call_started"
    call: ToolCall = None  # type: ignore[assignment]


@dataclass
class ToolCallFinishedEvent(AgentEvent):
    """工具调用执行结束。"""

    kind: ClassVar[str] = "tool_call_finished"
    call: ToolCall = None  # type: ignore[assignment]
    execution: ToolExecution = None  # type: ignore[assignment]


@dataclass
class ErrorEvent(AgentEvent):
    """本轮执行出错。"""

    kind: ClassVar[str] = "error"
    message: str = ""


@dataclass
class TurnCompletedEvent(AgentEvent):
    """一轮对话正常结束。"""

    kind: ClassVar[str] = "turn_completed"
    iterations: int = 0
