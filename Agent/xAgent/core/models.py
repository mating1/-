# -*- coding: utf-8 -*-
"""核心领域模型。

这些结构体是 core 层与所有前端（TUI / Web / Desktop / Mobile）之间
约定的数据契约，前端只依赖它们，不依赖任何具体实现。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

ROLE_SYSTEM = "system"
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_TOOL = "tool"


@dataclass
class ToolCall:
    """模型发起的一次工具调用。"""

    id: str
    name: str
    arguments: str = "{}"

    def parsed_arguments(self) -> Dict[str, Any]:
        """把 arguments 解析成字典，非法 JSON 时返回空字典。"""
        try:
            data = json.loads(self.arguments or "{}")
        except (ValueError, TypeError):
            return {}
        return data if isinstance(data, dict) else {}

    def to_api(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments or "{}"},
        }


@dataclass
class Message:
    """一条对话消息（兼容 OpenAI chat completions 的消息结构）。"""

    role: str
    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

    def to_api(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            payload["tool_calls"] = [call.to_api() for call in self.tool_calls]
        if self.tool_call_id:
            payload["tool_call_id"] = self.tool_call_id
        if self.name:
            payload["name"] = self.name
        return payload


@dataclass
class ToolExecution:
    """工具执行结果。

    ``ok`` 为 False 时 ``output`` 仍然是可直接回传给模型的错误描述，
    这样模型可以自行纠正参数后重试。
    """

    tool_name: str
    ok: bool
    output: str
    error: Optional[str] = None
