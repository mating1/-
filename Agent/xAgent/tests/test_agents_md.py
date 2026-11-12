# -*- coding: utf-8 -*-
"""AGENTS.md 注入：一次注入、缺失容错、长度截断单测。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.agent import Agent, MAX_AGENTS_CHARS  # noqa: E402
from core.session import Conversation  # noqa: E402
from core.tools.registry import ToolRegistry  # noqa: E402


class FakeClient:
    def stream(self, messages):
        yield  # pragma: no cover

    def tool_schemas(self):
        return []


def _make_agent(workspace: Path, agents_file: str = "AGENTS.md") -> Agent:
    return Agent(
        client=FakeClient(),
        registry=ToolRegistry(),
        conversation=Conversation(system_prompt="你是助手"),
        agents_file=agents_file,
        workspace=str(workspace),
    )


def test_missing_agents_file_is_tolerated(tmp_path):
    agent = _make_agent(tmp_path)
    assert all(m.name != "AGENTS.md" for m in agent.conversation.messages)


def test_agents_md_injected_once_and_truncated(tmp_path):
    (tmp_path / "AGENTS.md").write_text("约定内容 " * 5000, encoding="utf-8")
    agent = _make_agent(tmp_path)

    named = [m for m in agent.conversation.messages if m.name == "AGENTS.md"]
    assert len(named) == 1
    assert "已截断" in named[0].content
    assert len(named[0].content) <= MAX_AGENTS_CHARS + 120

    # reset 后仍只注入一次
    agent.reset()
    named = [m for m in agent.conversation.messages if m.name == "AGENTS.md"]
    assert len(named) == 1


def test_custom_agents_filename(tmp_path):
    (tmp_path / "RULES.md").write_text("自定义规则", encoding="utf-8")
    agent = _make_agent(tmp_path, agents_file="RULES.md")
    named = [m for m in agent.conversation.messages if m.name == "RULES.md"]
    assert len(named) == 1
    assert "自定义规则" in named[0].content
