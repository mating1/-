# -*- coding: utf-8 -*-
"""工具抽象层。

一个工具 = 名称 + 描述 + 参数 JSON Schema + 可执行函数。
工具本身与界面无关，任何前端都可以复用同一套工具。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


class Tool(ABC):
    """工具接口。"""

    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)

    @abstractmethod
    def run(self, **kwargs: Any) -> str:
        """执行工具，返回可直接回传给模型的文本结果。"""

    def to_schema(self) -> Dict[str, Any]:
        """转换成 OpenAI 兼容的 tools 描述。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters or {"type": "object", "properties": {}},
            },
        }


class FunctionTool(Tool):
    """把普通函数包装成工具。"""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        func: Callable[..., str],
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self._func = func

    def run(self, **kwargs: Any) -> str:
        return self._func(**kwargs)


@dataclass
class ToolSpec:
    """工具的静态描述（参数 schema）。"""

    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})

    def to_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


__all__ = ["FunctionTool", "Tool", "ToolSpec"]
