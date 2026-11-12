# -*- coding: utf-8 -*-
"""模型响应增量数据结构。

单独成模块，避免 client 与 protocol 之间的循环依赖。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass
class ToolCallDelta:
    """一次工具调用的流式分片。"""

    index: int = 0
    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class LLMDelta:
    """模型响应的一个增量片段。"""

    content: str = ""
    tool_calls: Tuple[ToolCallDelta, ...] = ()
    finish_reason: Optional[str] = None
    raw: dict = field(default_factory=dict, repr=False)
