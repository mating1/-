# -*- coding: utf-8 -*-
"""LLM 交互层。

只负责"把消息发给模型、把模型的流式响应拆成增量"，不关心工具如何执行、
也不关心界面如何展示。
"""

from .client import LLMClient
from .deltas import LLMDelta, ToolCallDelta
from .protocol import BaseLLMClient, LLMClientProtocol
from .streaming import ToolCallAccumulator

__all__ = [
    "BaseLLMClient",
    "LLMClient",
    "LLMClientProtocol",
    "LLMDelta",
    "ToolCallAccumulator",
    "ToolCallDelta",
]
