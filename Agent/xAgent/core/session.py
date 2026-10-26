# -*- coding: utf-8 -*-
"""对话历史管理。

负责保存上下文消息，并把历史转换成模型接口需要的消息数组。
"""

from __future__ import annotations

from typing import List, Optional

from .models import Message, ToolCall, ROLE_ASSISTANT, ROLE_SYSTEM, ROLE_TOOL, ROLE_USER


class Conversation:
    """单个会话的上下文容器。"""

    def __init__(self, system_prompt: str = "") -> None:
        self.system_prompt = system_prompt
        self._messages: List[Message] = []

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    def add_user(self, content: str) -> Message:
        message = Message(role=ROLE_USER, content=content)
        self._messages.append(message)
        return message

    def add_assistant(
        self,
        content: str = "",
        tool_calls: Optional[List[ToolCall]] = None,
    ) -> Message:
        message = Message(
            role=ROLE_ASSISTANT,
            content=content,
            tool_calls=list(tool_calls or []),
        )
        self._messages.append(message)
        return message

    def add_tool_result(self, call: ToolCall, content: str) -> Message:
        message = Message(
            role=ROLE_TOOL,
            content=content,
            tool_call_id=call.id,
            name=call.name,
        )
        self._messages.append(message)
        return message

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------
    @property
    def messages(self) -> List[Message]:
        return list(self._messages)

    def to_messages(self, system_prompt: Optional[str] = None) -> List[Message]:
        """生成发送给模型的完整消息列表（含可选的系统提示词）。"""
        prompt = self.system_prompt if system_prompt is None else system_prompt
        payload: List[Message] = []
        if prompt:
            payload.append(Message(role=ROLE_SYSTEM, content=prompt))
        payload.extend(self._messages)
        return payload

    def clear(self) -> None:
        """清空上下文，但保留系统提示词。"""
        self._messages.clear()

    def __len__(self) -> int:
        return len(self._messages)
