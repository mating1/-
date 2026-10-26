# -*- coding: utf-8 -*-
"""Agent 编排层。

Agent 是 core 的门面：接收用户输入 → 调模型 → 执行工具 → 回传结果 → 循环，
并把整个过程以事件流的形式输出。它不认识任何界面，
TUI / Web / Desktop 都只是它的一个消费者。
"""

from __future__ import annotations

from typing import AsyncIterator, Iterator, List, Optional

from .errors import LLMError
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
from .llm.deltas import LLMDelta
from .llm.streaming import ToolCallAccumulator
from .models import Message
from .session import Conversation
from .tools.registry import ToolRegistry
from .utils.asyncbridge import iterate_in_thread


class Agent:
    """带工具调用能力的对话代理。"""

    def __init__(
        self,
        client,
        registry: ToolRegistry,
        conversation: Optional[Conversation] = None,
        max_iterations: int = 8,
        system_prompt: str = "",
    ) -> None:
        self.client = client
        self.registry = registry
        self.max_iterations = max_iterations
        self.conversation = conversation or Conversation(system_prompt=system_prompt)
        if system_prompt:
            self.conversation.system_prompt = system_prompt

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------
    def run(self, prompt: str) -> Iterator[AgentEvent]:
        """执行一轮对话，产出事件流（同步接口）。"""
        prompt = (prompt or "").strip()
        if not prompt:
            yield ErrorEvent(message="提示词不能为空")
            return

        self.conversation.add_user(prompt)
        yield UserMessageEvent(text=prompt)

        for iteration in range(1, self.max_iterations + 1):
            messages = self.conversation.to_messages()
            accumulator = ToolCallAccumulator()
            chunks: List[str] = []

            try:
                for delta in self.client.stream(messages):
                    self._absorb(delta, accumulator, chunks)
                    if delta.content:
                        yield AssistantDeltaEvent(text=delta.content)
            except LLMError as exc:
                yield ErrorEvent(message=str(exc))
                return
            except Exception as exc:  # noqa: BLE001 - 保证异常不会击穿会话
                yield ErrorEvent(message="模型调用异常：%s" % exc)
                return

            content = "".join(chunks)
            tool_calls = accumulator.build()

            if not tool_calls:
                self.conversation.add_assistant(content)
                yield AssistantMessageEvent(text=content)
                yield TurnCompletedEvent(iterations=iteration)
                return

            self.conversation.add_assistant(content, tool_calls=tool_calls)
            for call in tool_calls:
                yield ToolCallStartedEvent(call=call)
                execution = self.registry.execute_call(call)
                self.conversation.add_tool_result(call, execution.output)
                yield ToolCallFinishedEvent(call=call, execution=execution)

        yield ErrorEvent(message="已达到最大迭代次数（%d），本轮任务未完成" % self.max_iterations)

    async def arun(self, prompt: str) -> AsyncIterator[AgentEvent]:
        """执行一轮对话，产出事件流（异步接口，供 TUI / Web 使用）。"""
        async for event in iterate_in_thread(lambda: self.run(prompt)):
            yield event

    # ------------------------------------------------------------------
    # 会话管理
    # ------------------------------------------------------------------
    def reset(self) -> None:
        """清空对话历史，保留系统提示词。"""
        self.conversation.clear()

    @property
    def history(self) -> List[Message]:
        return self.conversation.messages

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    @staticmethod
    def _absorb(delta: LLMDelta, accumulator: ToolCallAccumulator, chunks: List[str]) -> None:
        """把一个流式增量并入内容缓冲与工具调用累加器。"""
        if delta.content:
            chunks.append(delta.content)
        for tool_delta in delta.tool_calls:
            accumulator.feed(tool_delta)
