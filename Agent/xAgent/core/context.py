# -*- coding: utf-8 -*-
"""上下文压缩与历史归档。

职责：
- 估算当前会话的 Token 用量，并判断是否达到告警/封锁阈值；
- 压缩前把原始上下文完整归档到 ``.agents/context/<编号>.jsonl``；
- 调用 LLM 生成工作摘要（不带工具，纯摘要任务）；
- 用摘要替换历史消息，并追加归档说明；
- 提供对归档文件的本地全文关键词检索（供 recallContext 工具使用）。

本模块不依赖任何界面框架，只被 core 层与工具层复用。
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import LLMConfig
from .errors import LLMError
from .models import Message, ToolCall, ROLE_ASSISTANT

DEFAULT_CONTEXT_WINDOW = 128000
COMPACT_THRESHOLD = 0.7
ARCHIVE_DIRNAME = ("agents", "context")
ARCHIVE_NOTE_TEMPLATE = (
    "此前上下文已于 {time} 完成压缩，原始上下文保存在编号为 {archive_id} 的归档文件中。"
    "如需查找历史信息，请使用 recallContext 工具。"
)

COMPACT_SYSTEM_PROMPT = """你是一名 AI Agent 的上下文管理助手。当前会话即将达到上下文窗口限制，需要将历史对话压缩为一份高质量的工作摘要，以便 Agent 在新的上下文中继续执行任务。

请认真阅读提供的历史上下文，提取对后续工作仍然有价值的信息，并生成一份约 5,000 Tokens 的 Markdown 摘要。

摘要应重点保留以下内容：

1. **用户目标与要求**：用户希望完成什么任务？有哪些必须遵守的约束、偏好和验收条件？
2. **已经完成的工作**：哪些任务已经完成？实现了哪些功能？获得了哪些已经验证的结果？
3. **当前工作状态**：Agent 正在处理什么任务？当前进展到哪一步？是否存在尚未解决的问题？
4. **关键技术信息**：保留重要的文件路径、函数名称、接口定义、配置项、执行命令、错误信息和必要的代码片段。
5. **关键决策与原因**：记录用户和 Agent 已经确定的技术方案，以及重要的设计取舍。
6. **下一步任务**：明确接下来应该执行的操作，以及需要继续验证的事项。

请遵守以下要求：

- 优先保留对后续任务有直接影响的信息，删除寒暄、重复讨论、过时的尝试和无关内容。
- 对已经验证的事实与尚未验证的推测作出明确区分。
- 不要将计划完成的任务描述为已经完成。
- 重要的文件路径、函数名称、配置名称和命令应保留准确原文。
- 对失败的尝试，只保留有助于避免重复错误的信息。
- 如果信息存在冲突，应优先保留用户最新确认的要求，并简要说明仍然存在的冲突。
- 如果某些历史细节无法在摘要中完整保留，可简要说明它们已保存到原始上下文归档中，后续可以通过 recallContext 工具重新检索。
- 使用清晰的 Markdown 结构输出摘要，不要附加解释或无关内容。

**最终目标：使一个从未阅读过原始对话的 Agent，仅凭这份摘要，就能够理解当前任务、继承关键决策，并继续开展工作。**"""


def estimate_tokens(text: str) -> int:
    """粗略估算一段文本的 Token 数（中文按字符计，英文按 4 字符≈1）。"""
    if not text:
        return 0
    ascii_chars = 0
    other_chars = 0
    for ch in text:
        if ord(ch) < 128:
            ascii_chars += 1
        else:
            other_chars += 1
    return int(ascii_chars / 4.0 + other_chars * 1.2 + 1)


def messages_tokens(messages: List[Message], system_prompt: str = "") -> int:
    """累计一组消息的估算 Token 数（含系统提示词、工具参数与工具结果）。"""
    total = estimate_tokens(system_prompt)
    for message in messages:
        total += estimate_tokens(message.content)
        total += estimate_tokens(message.role)
        for call in message.tool_calls:
            total += estimate_tokens(call.name) + estimate_tokens(call.arguments)
    return total


class ContextManager:
    """上下文用量、归档、摘要与检索的统一入口。"""

    def __init__(
        self,
        workspace: str,
        llm: LLMConfig,
        window_tokens: int = DEFAULT_CONTEXT_WINDOW,
        threshold: float = COMPACT_THRESHOLD,
        window_is_default: bool = True,
        archive_dirname: str = str(Path(*ARCHIVE_DIRNAME)),
        recall_limit: int = 8,
        recall_snippet: int = 240,
    ) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.archive_dir = self.workspace.joinpath(*Path(archive_dirname).parts)
        self.llm = llm
        self.window_tokens = int(window_tokens or DEFAULT_CONTEXT_WINDOW)
        self.threshold = threshold
        self.window_is_default = window_is_default
        self.recall_limit = int(recall_limit or 8)
        self.recall_snippet = int(recall_snippet or 240)
        # 最近一次模型 API 返回的用量（本轮发送的上下文总量），优先采用
        self.last_api_tokens = 0

    # ------------------------------------------------------------------
    # 用量监控
    # ------------------------------------------------------------------
    def used_tokens(self, messages: List[Message], system_prompt: str = "") -> int:
        """当前上下文用量：优先 API 值，否则本地估算。"""
        if self.last_api_tokens > 0:
            return self.last_api_tokens
        return messages_tokens(messages, system_prompt)

    def percent(self, used: int) -> float:
        if self.window_tokens <= 0:
            return 0.0
        return min(100.0, used * 100.0 / self.window_tokens)

    def status(self, messages: List[Message], system_prompt: str = "") -> Dict[str, object]:
        used = self.used_tokens(messages, system_prompt)
        pct = self.percent(used)
        return {
            "used": used,
            "window": self.window_tokens,
            "percent": pct,
            "warning": pct >= self.threshold * 100.0,
            "limit": pct >= self.threshold * 100.0,
            "window_is_default": self.window_is_default,
        }

    # ------------------------------------------------------------------
    # 归档
    # ------------------------------------------------------------------
    def new_archive_id(self) -> str:
        return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

    def save_archive(self, messages: List[Message], system_prompt: str, archive_id: str) -> Path:
        """把原始上下文完整写入 jsonl；返回文件路径。"""
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        path = self.archive_dir / ("%s.jsonl" % archive_id)
        with path.open("w", encoding="utf-8") as handle:
            if system_prompt:
                handle.write(
                    json.dumps(
                        {"order": 0, "role": "system", "content": system_prompt},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            for index, message in enumerate(messages, start=1):
                record = {"order": index, "role": message.role, "content": message.content}
                if message.tool_calls:
                    record["tool_calls"] = [
                        {"id": call.id, "name": call.name, "arguments": call.arguments}
                        for call in message.tool_calls
                    ]
                if message.tool_call_id:
                    record["tool_call_id"] = message.tool_call_id
                if message.name:
                    record["name"] = message.name
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return path

    # ------------------------------------------------------------------
    # 摘要生成
    # ------------------------------------------------------------------
    def render_history(self, messages: List[Message]) -> str:
        """把历史消息渲染成供压缩模型阅读的纯文本。"""
        blocks: List[str] = []
        for message in messages:
            role = message.role
            parts = ["[%s] %s" % (role, message.content)]
            for call in message.tool_calls:
                parts.append("  调用工具 %s，参数 %s" % (call.name, call.arguments))
            if message.tool_call_id:
                parts.append("  （工具调用返回，id=%s，工具=%s）" % (message.tool_call_id, message.name or ""))
            blocks.append("\n".join(parts))
        return "\n\n".join(blocks)

    def generate_summary(self, messages: List[Message]) -> str:
        """调用 LLM 生成摘要（不带工具，纯摘要任务）。"""
        import requests

        history = self.render_history(messages)
        payload = {
            "model": self.llm.model,
            "messages": [
                {"role": "system", "content": COMPACT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": "以下是需要压缩的历史上下文：\n\n" + history,
                },
            ],
            "stream": False,
        }
        try:
            response = requests.post(
                self.llm.endpoint,
                headers={
                    "Authorization": "Bearer " + self.llm.api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.llm.timeout,
            )
        except requests.RequestException as exc:
            raise LLMError("压缩请求失败：%s" % exc) from exc
        if response.status_code != 200:
            raise LLMError("压缩请求返回 HTTP %s：%s" % (response.status_code, response.text[:300]))
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("压缩响应解析失败：%s" % exc) from exc
        return (content or "").strip()

    # ------------------------------------------------------------------
    # 替换历史
    # ------------------------------------------------------------------
    @staticmethod
    def build_compacted_message(summary: str, archive_id: str, timestamp: str) -> Message:
        note = ARCHIVE_NOTE_TEMPLATE.format(time=timestamp, archive_id=archive_id)
        return Message(role=ROLE_ASSISTANT, content="%s\n\n%s" % (summary.strip(), note))

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------
    def list_archives(self) -> List[Path]:
        if not self.archive_dir.is_dir():
            return []
        return sorted(self.archive_dir.glob("*.jsonl"))

    def search(self, text: str, archive_id: Optional[str] = None, limit: Optional[int] = None,
               snippet_len: Optional[int] = None) -> str:
        """在归档文件中做本地全文关键词检索，返回有限长度的片段。"""
        limit = int(limit or self.recall_limit)
        snippet_len = int(snippet_len or self.recall_snippet)
        keyword = (text or "").strip()
        if not keyword:
            return "检索词为空。"
        targets = self.list_archives()
        if archive_id:
            target = self.archive_dir / ("%s.jsonl" % archive_id.strip())
            if not target.is_file():
                return "未找到编号为 %s 的归档文件。" % archive_id
            targets = [target]
        if not targets:
            return "尚未生成任何上下文归档。"

        hits: List[str] = []
        for path in targets:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError as exc:
                hits.append("[%s] 读取失败：%s" % (path.stem, exc))
                continue
            for line_no, line in enumerate(lines, start=1):
                if keyword.lower() not in line.lower():
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                role = record.get("role", "?")
                content = str(record.get("content", ""))
                compact = re.sub(r"\s+", " ", content).strip()
                if len(compact) > snippet_len:
                    compact = compact[:snippet_len] + "…"
                hits.append(
                    "[归档 %s · 第 %d 行 · %s] %s" % (path.stem, line_no, role, compact)
                )
                if len(hits) >= limit:
                    break
            if len(hits) >= limit:
                break

        if not hits:
            return "未找到包含“%s”的历史内容。" % keyword
        header = "在 %d 个归档文件中检索到以下片段（最多显示 %d 条）：\n\n" % (len(targets), limit)
        return header + "\n".join(hits)
