# -*- coding: utf-8 -*-
"""Agent 编排层。

Agent 是 core 的门面：接收用户输入 → 调模型 → 执行工具 → 回传结果 → 循环，
并把整个过程以事件流的形式输出。它不认识任何界面，
TUI / Web / Desktop 都只是它的一个消费者。
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import AsyncIterator, Iterator, List, Optional

from .context import ContextManager
from .errors import LLMError
from .events import (
    AgentEvent,
    AssistantDeltaEvent,
    AssistantMessageEvent,
    CompactFailedEvent,
    CompactFinishedEvent,
    CompactStartedEvent,
    ContextUsageEvent,
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

MAX_AGENTS_CHARS = 8000


class Agent:
    """带工具调用能力的对话代理。"""

    def __init__(
        self,
        client,
        registry: ToolRegistry,
        conversation: Optional[Conversation] = None,
        max_iterations: int = 8,
        system_prompt: str = "",
        context_manager: Optional[ContextManager] = None,
        mcp_bridge=None,
        session_store=None,
        agents_file: str = "AGENTS.md",
        workspace: str = ".",
    ) -> None:
        self.client = client
        self.registry = registry
        self.max_iterations = max_iterations
        self.conversation = conversation or Conversation(system_prompt=system_prompt)
        if system_prompt:
            self.conversation.system_prompt = system_prompt
        self.context = context_manager
        self.mcp_bridge = mcp_bridge
        self.session_store = session_store
        self.agents_file = agents_file or "AGENTS.md"
        self.workspace = workspace or "."
        self.session_title = ""
        self._inject_agents_md()

    def set_session_title(self, title: str) -> None:
        """用户指定本次会话名称。"""
        self.session_title = (title or "").strip()[:40]

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

            # 每次模型完成响应后检查上下文用量
            self._update_context_usage()
            yield self._context_event()

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
    # 上下文压缩与监控
    # ------------------------------------------------------------------
    def context_status(self) -> dict:
        """返回当前上下文用量状态（用于 TUI 状态栏与阈值判断）。"""
        if self.context is None:
            return {
                "used": 0,
                "window": 0,
                "percent": 0.0,
                "warning": False,
                "limit": False,
                "window_is_default": True,
            }
        return self.context.status(self.conversation.messages, self.conversation.system_prompt)

    def context_limit_reached(self) -> bool:
        return bool(self.context_status().get("limit"))

    def compact(self) -> Iterator[AgentEvent]:
        """执行一次上下文压缩（归档 → LLM 摘要 → 替换历史）。"""
        yield CompactStartedEvent()
        if self.context is None:
            yield CompactFailedEvent(message="未配置上下文管理器，无法压缩")
            return

        conversation = self.conversation
        messages = conversation.messages
        if not messages:
            yield CompactFailedEvent(message="当前上下文为空，无需压缩")
            return

        try:
            archive_id = self.context.new_archive_id()
            path = self.context.save_archive(messages, conversation.system_prompt, archive_id)
            if not path.exists() or path.stat().st_size == 0:
                yield CompactFailedEvent(message="原始上下文归档失败，已保留原上下文")
                return

            summary = self.context.generate_summary(messages)
            if not summary:
                yield CompactFailedEvent(message="LLM 未生成有效摘要，已保留原上下文")
                return

            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            compacted = self.context.build_compacted_message(summary, archive_id, timestamp)
            before_text = self.context.render_history(messages)
            conversation.replace_messages([compacted])
            self.context.last_api_tokens = 0
            yield CompactFinishedEvent(
                archive_id=archive_id,
                summary=summary,
                before=before_text,
                after=compacted.content,
            )
        except Exception as exc:  # noqa: BLE001 - 压缩失败必须保留原上下文
            yield CompactFailedEvent(message="压缩失败：%s" % exc)

    async def acompact(self) -> AsyncIterator[AgentEvent]:
        """压缩的异步接口。"""
        async for event in iterate_in_thread(lambda: self.compact()):
            yield event

    def _update_context_usage(self) -> None:
        """用模型 API 返回的用量更新上下文统计（拿不到则沿用估算）。"""
        if self.context is None:
            return
        usage = getattr(self.client, "last_usage", None) or {}
        total = usage.get("total_tokens")
        if not total:
            total = (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0)
        if total:
            self.context.last_api_tokens = int(total)

    def _context_event(self) -> ContextUsageEvent:
        status = self.context_status()
        return ContextUsageEvent(
            used=status["used"],
            window=status["window"],
            percent=status["percent"],
            warning=status["warning"],
            limit=status["limit"],
            window_is_default=status["window_is_default"],
        )

    # ------------------------------------------------------------------
    # 会话管理
    # ------------------------------------------------------------------
    def reset(self) -> None:
        """清空对话历史（保留系统提示词，并重新注入 AGENTS.md）。"""
        self.conversation.clear()
        self._inject_agents_md()

    def _inject_agents_md(self) -> None:
        """会话首次加载时把项目 AGENTS.md 作为一条消息注入，后续轮次直接复用。

        只注入一次、且位于历史最前，保证前缀稳定，缓存有效；
        恢复会话时历史里已有该消息，不会重复注入。
        """
        try:
            path = Path(self.workspace) / self.agents_file
            if not path.is_file() or self.conversation.has_named(self.agents_file):
                return
            content = path.read_text(encoding="utf-8").strip()
        except OSError:
            return
        if content:
            if len(content) > MAX_AGENTS_CHARS:
                content = content[:MAX_AGENTS_CHARS] + "\n\n（项目约定文件过长，已截断至 %d 字符）" % MAX_AGENTS_CHARS
            self.conversation.prepend_system_message(
                "[项目约定文件 %s 已注入，请全程遵守]\n\n%s" % (self.agents_file, content),
                name=self.agents_file,
            )

    # ------------------------------------------------------------------
    # MCP 异步加载（TUI 先渲染界面，再在后台线程调用本方法补上工具）
    # ------------------------------------------------------------------
    def load_mcp(self) -> dict:
        bridge = self.mcp_bridge
        if bridge is None:
            return {"available": False, "servers": {}, "tool_count": 0}
        try:
            if bridge.available and not getattr(bridge, "_started", False):
                bridge.start()
            from .tools.mcp.toolset import make_mcp_tools

            for tool in make_mcp_tools(bridge):
                self.registry.register(tool)
            if hasattr(self.client, "set_tool_schemas"):
                self.client.set_tool_schemas(self.registry.schemas())
        except Exception as exc:  # noqa: BLE001 - MCP 失败不能影响主流程
            return {"available": bridge.available, "servers": {}, "tool_count": 0, "error": str(exc)}
        return bridge.status()

    def mcp_status(self) -> dict:
        if self.mcp_bridge is None:
            return {"available": False, "servers": {}, "tool_count": 0}
        return self.mcp_bridge.status()

    # ------------------------------------------------------------------
    # 会话存档
    # ------------------------------------------------------------------
    def save_session(self) -> Optional[Path]:
        if self.session_store is None:
            return None
        return self.session_store.save(
            self.conversation.messages,
            self.conversation.system_prompt,
            title=self.session_title,
        )

    def new_session(self, auto_save: bool = True) -> Optional[Path]:
        """新建会话；开启自动保存时先把当前历史存档。"""
        saved = None
        if auto_save and self.session_store and self.conversation.messages:
            saved = self.session_store.save(
                self.conversation.messages,
                self.conversation.system_prompt,
                title=self.session_title,
            )
        self.session_title = ""
        self.reset()
        return saved

    def restore_session(self, session_id: str) -> None:
        if self.session_store is None:
            raise RuntimeError("未配置会话存档")
        system_prompt, messages = self.session_store.load(session_id)
        if system_prompt:
            self.conversation.system_prompt = system_prompt
        self.conversation.replace_messages(messages)
        if self.context is not None:
            self.context.last_api_tokens = 0

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
