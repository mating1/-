# -*- coding: utf-8 -*-
"""流式工具调用的增量聚合。

模型在流式响应中会把一次工具调用的 id / name / arguments 拆成多个
分片返回，这里负责把它们合并成完整的 ToolCall 列表。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from ..models import ToolCall


@dataclass
class ToolCallAccumulator:
    """聚合流式返回的工具调用分片。"""

    _slots: Dict[int, dict] = field(default_factory=dict, repr=False)

    def feed(self, delta) -> None:
        """接收一个工具调用分片。"""
        index = int(getattr(delta, "index", 0) or 0)
        slot = self._slots.setdefault(index, {"id": "", "name": "", "arguments": ""})
        if getattr(delta, "id", ""):
            slot["id"] = delta.id
        if getattr(delta, "name", ""):
            slot["name"] = delta.name
        if getattr(delta, "arguments", ""):
            slot["arguments"] += delta.arguments

    def build(self) -> List[ToolCall]:
        """输出聚合后的工具调用列表。"""
        calls: List[ToolCall] = []
        for index in sorted(self._slots):
            slot = self._slots[index]
            call_id = slot["id"] or "call_%d" % index
            calls.append(
                ToolCall(
                    id=call_id,
                    name=slot["name"],
                    arguments=slot["arguments"] or "{}",
                )
            )
        return calls
