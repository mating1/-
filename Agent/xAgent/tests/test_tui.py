# -*- coding: utf-8 -*-
"""TUI 前端冒烟测试（Textual headless 模式）。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.agent import Agent  # noqa: E402
from core.config import AppConfig, LLMConfig  # noqa: E402
from core.llm.deltas import LLMDelta, ToolCallDelta  # noqa: E402
from core.session import Conversation  # noqa: E402
from core.tools.registry import ToolRegistry  # noqa: E402
from tui.app import XAgentApp  # noqa: E402
from textual.widgets import Input, Markdown  # noqa: E402


class ScriptedClient:
    def __init__(self, scripts):
        self.scripts = list(scripts)

    def stream(self, messages):
        for delta in self.scripts.pop(0):
            yield delta

    def tool_schemas(self):
        return []


def _build_app(scripts):
    config = AppConfig(
        llm=LLMConfig(base_url="http://localhost/v1", api_key="test-key", model="test-model"),
        system_prompt="你是测试助手",
        max_iterations=3,
    )
    agent = Agent(
        client=ScriptedClient(scripts),
        registry=ToolRegistry(),
        conversation=Conversation(system_prompt=config.system_prompt),
        max_iterations=config.max_iterations,
        system_prompt=config.system_prompt,
    )
    return XAgentApp(agent=agent, config=config)


def test_tui_renders_user_and_assistant_messages():
    async def scenario():
        app = _build_app([[LLMDelta(content="你好，"), LLMDelta(content="我是 xAgent")]])
        async with app.run_test() as pilot:
            prompt = app.query_one("#prompt", Input)
            prompt.focus()
            await pilot.pause()
            prompt.value = "你好"
            await pilot.press("enter")
            await pilot.pause()
            for _ in range(20):
                await pilot.pause()
                if app.query_one("#prompt", Input).disabled is False:
                    break
            await pilot.pause()

            markdown_texts = [str(widget.source) for widget in app.query(Markdown)]
            assert any("你好，我是 xAgent" in text for text in markdown_texts)

            bubble_texts = [str(widget.content) for widget in app.query(".user-bubble")]
            assert any("你好" in text for text in bubble_texts)

    asyncio.run(scenario())


def test_tui_renders_tool_call_card():
    async def scenario():
        app = _build_app(
            [
                [
                    LLMDelta(
                        tool_calls=(
                            ToolCallDelta(
                                index=0,
                                id="call_1",
                                name="listDir",
                                arguments='{"path": "."}',
                            ),
                        )
                    )
                ],
                [LLMDelta(content="目录内容如上")],
            ]
        )
        async with app.run_test() as pilot:
            prompt = app.query_one("#prompt", Input)
            prompt.focus()
            await pilot.pause()
            prompt.value = "列出目录"
            await pilot.press("enter")
            for _ in range(30):
                await pilot.pause()
                if not app.query_one("#prompt", Input).disabled:
                    break
            await pilot.pause()

            cards = list(app.query(".tool-card"))
            assert len(cards) == 1
            assert "listDir" in str(cards[0].title)

    asyncio.run(scenario())
