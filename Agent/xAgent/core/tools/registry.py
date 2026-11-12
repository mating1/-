# -*- coding: utf-8 -*-
"""工具注册表与执行器。

职责边界：
- 注册表只关心"有哪些工具、参数怎么解析、执行结果怎么包装"；
- 具体的业务逻辑放在各自的工具服务里（如 fileops.service）。
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Iterable, List, Optional

from .. import tracing
from ..errors import ToolError
from ..models import ToolCall, ToolExecution
from .base import Tool


class ToolRegistry:
    """工具注册表。"""

    def __init__(self, tools: Optional[Iterable[Tool]] = None) -> None:
        self._tools: Dict[str, Tool] = {}
        for tool in tools or ():
            self.register(tool)

    # ------------------------------------------------------------------
    # 注册
    # ------------------------------------------------------------------
    def register(self, tool: Tool) -> None:
        if not tool.name:
            raise ToolError("工具必须有名称")
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    @property
    def names(self) -> List[str]:
        return list(self._tools.keys())

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def schemas(self) -> List[dict]:
        """返回给模型的工具 schema 列表。"""
        return [tool.to_schema() for tool in self._tools.values()]

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------
    def execute(self, name: str, arguments_json: str = "{}") -> ToolExecution:
        """按名称执行工具，任何异常都会被转换成失败结果而不是抛出。"""
        started = time.perf_counter()
        tool = self._tools.get(name)
        if tool is None:
            message = "未知的 tool：%s（可用工具：%s）" % (
                name,
                ", ".join(self.names) or "无",
            )
            self._trace(name, "unknown_tool", started, {"arguments": arguments_json})
            return ToolExecution(tool_name=name, ok=False, output=message, error=message)

        try:
            arguments = self._parse_arguments(arguments_json)
        except ToolError as exc:
            self._trace(name, "bad_arguments", started, {"arguments": arguments_json})
            return ToolExecution(tool_name=name, ok=False, output=str(exc), error=str(exc))

        try:
            output = tool.run(**arguments)
        except ToolError as exc:
            self._trace(name, "tool_error", started, {"arguments": arguments, "error": str(exc)})
            return ToolExecution(tool_name=name, ok=False, output=str(exc), error=str(exc))
        except TypeError as exc:
            message = "%s 参数缺失或类型错误：%s" % (name, exc)
            self._trace(name, "type_error", started, {"arguments": arguments, "error": message})
            return ToolExecution(tool_name=name, ok=False, output=message, error=message)
        except OSError as exc:
            message = "文件操作失败：%s" % exc
            self._trace(name, "os_error", started, {"arguments": arguments, "error": message})
            return ToolExecution(tool_name=name, ok=False, output=message, error=message)
        except Exception as exc:  # noqa: BLE001 - 兜底，避免中断整个会话
            message = "%s 执行异常：%s" % (name, exc)
            self._trace(name, "exception", started, {"arguments": arguments, "error": message})
            return ToolExecution(tool_name=name, ok=False, output=message, error=message)

        self._trace(name, "ok", started, {"arguments": arguments, "output": output})
        return ToolExecution(tool_name=name, ok=True, output=output or "")

    def execute_call(self, call: ToolCall) -> ToolExecution:
        """执行一个模型发起的工具调用。"""
        return self.execute(call.name, call.arguments)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    @staticmethod
    def _trace(name: str, status: str, started: float, detail: Any = None) -> None:
        """把本次调用写进追踪日志，耗时以毫秒计。"""
        tracing.record_tool_call(
            tool_name=name,
            status=status,
            duration_ms=(time.perf_counter() - started) * 1000,
            detail=detail,
        )

    @staticmethod
    def _parse_arguments(arguments_json: str) -> Dict[str, Any]:
        raw = (arguments_json or "{}").strip() or "{}"
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise ToolError("工具参数不是合法 JSON：%s（收到：%s）" % (exc, raw)) from exc
        if not isinstance(data, dict):
            raise ToolError("工具参数必须是 JSON 对象：%s" % raw)
        return data


__all__ = ["ToolRegistry"]
