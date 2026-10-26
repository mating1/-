# -*- coding: utf-8 -*-
"""LLM 客户端协议。

定义 core 层对"大模型"的最小抽象，方便未来接入不同厂商的实现，
而无需改动上层 Agent 与各前端。
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Iterator, List, Protocol, runtime_checkable

from ..models import Message
from .deltas import LLMDelta


@runtime_checkable
class LLMClientProtocol(Protocol):
    """大模型客户端协议。"""

    def stream(self, messages: List[Message]) -> Iterator[LLMDelta]:
        """同步流式请求，逐个返回响应增量。"""
        ...

    def astream(self, messages: List[Message]) -> AsyncIterator[LLMDelta]:
        """异步流式请求，逐个返回响应增量。"""
        ...

    def tool_schemas(self) -> List[dict]:
        """返回当前客户端可用的工具 schema（JSON Schema 格式）。"""
        ...


class BaseLLMClient:
    """协议基类：提供默认的工具 schema 管理能力。"""

    def __init__(self, tool_schemas: List[dict] | None = None) -> None:
        self._tool_schemas: List[dict] = list(tool_schemas or [])

    def tool_schemas(self) -> List[dict]:
        return list(self._tool_schemas)

    def set_tool_schemas(self, schemas: List[dict]) -> None:
        self._tool_schemas = list(schemas or [])

    def _payload(self, messages: List[Message], extra: dict | None = None) -> dict:
        payload: dict[str, Any] = {
            "model": getattr(self, "model", ""),
            "messages": [message.to_api() for message in messages],
            "stream": True,
        }
        if self._tool_schemas:
            payload["tools"] = self._tool_schemas
        if extra:
            payload.update(extra)
        return payload
