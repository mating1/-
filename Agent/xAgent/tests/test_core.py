# -*- coding: utf-8 -*-
"""core 层单元测试。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.agent import Agent  # noqa: E402
from core.errors import ToolError  # noqa: E402
from core.events import (  # noqa: E402
    AssistantDeltaEvent,
    AssistantMessageEvent,
    ToolCallFinishedEvent,
    ToolCallStartedEvent,
    UserMessageEvent,
)
from core.llm.client import LLMDelta, ToolCallDelta  # noqa: E402
from core.models import ToolCall  # noqa: E402
from core.session import Conversation  # noqa: E402
from core.tools.fileops import FileSystemService, build_file_tools  # noqa: E402
from core.tools.registry import ToolRegistry  # noqa: E402


class FakeClient:
    """按预设脚本产出流式增量的假客户端。"""

    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.requests = []

    def stream(self, messages):
        self.requests.append(messages)
        for delta in self.scripts.pop(0):
            yield delta

    def tool_schemas(self):
        return []


def _tool_delta(index=0, call_id="call_1", name="readFile", arguments="{}"):
    return LLMDelta(
        content="",
        tool_calls=(ToolCallDelta(index=index, id=call_id, name=name, arguments=arguments),),
    )


def test_file_service_crud(tmp_path):
    service = FileSystemService()

    created = service.create_file(str(tmp_path), "demo.txt", "hello world")
    assert "已创建文件" in created
    assert (tmp_path / "demo.txt").read_text(encoding="utf-8") == "hello world"

    assert "hello world" in service.read_file(str(tmp_path / "demo.txt"))
    assert "是否纯文本：是" in service.get_file_type(str(tmp_path / "demo.txt"))

    edited = service.edit_file(str(tmp_path / "demo.txt"), "world", "xAgent")
    assert "替换 1 处" in edited
    assert (tmp_path / "demo.txt").read_text(encoding="utf-8") == "hello xAgent"

    listing = service.list_dir(str(tmp_path))
    assert "[FILE] demo.txt" in listing


def test_file_service_errors(tmp_path):
    service = FileSystemService()

    try:
        service.read_file(str(tmp_path / "missing.txt"))
    except ToolError as exc:
        assert "文件不存在" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("应当抛出 ToolError")

    try:
        service.create_file(str(tmp_path), "sub/demo.txt")
    except ToolError as exc:
        assert "路径分隔符" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("应当抛出 ToolError")

    target = tmp_path / "dup.txt"
    target.write_text("x", encoding="utf-8")
    try:
        service.create_file(str(tmp_path), "dup.txt")
    except ToolError as exc:
        assert "未覆盖" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("应当抛出 ToolError")


def test_registry_handles_bad_arguments(tmp_path):
    registry = ToolRegistry(build_file_tools(FileSystemService()))

    unknown = registry.execute("nope", "{}")
    assert unknown.ok is False
    assert "未知的 tool" in unknown.output

    invalid_json = registry.execute("readFile", "{not json}")
    assert invalid_json.ok is False
    assert "合法 JSON" in invalid_json.output

    missing_param = registry.execute("readFile", "{}")
    assert missing_param.ok is False

    ok = registry.execute("createFile", json.dumps({"directory": str(tmp_path), "filename": "a.txt"}))
    assert ok.ok is True
    assert "已创建文件" in ok.output


def test_agent_runs_tool_then_answers(tmp_path):
    client = FakeClient(
        [
            [_tool_delta(arguments=json.dumps({"path": str(tmp_path / "demo.txt")}))],
            [LLMDelta(content="已经读取完毕")],
        ]
    )
    (tmp_path / "demo.txt").write_text("hello", encoding="utf-8")

    registry = ToolRegistry(build_file_tools(FileSystemService()))
    agent = Agent(
        client=client,
        registry=registry,
        conversation=Conversation(system_prompt="你是助手"),
        max_iterations=4,
    )

    events = list(agent.run("读取 demo.txt"))

    kinds = [event.kind for event in events]
    assert kinds[0] == "user_message"
    assert "tool_call_started" in kinds
    assert "tool_call_finished" in kinds
    assert kinds[-1] == "turn_completed"

    finished = [e for e in events if isinstance(e, ToolCallFinishedEvent)][0]
    assert finished.execution.ok is True
    assert "hello" in finished.execution.output

    messages = [m for m in agent.conversation.messages]
    assert messages[-1].role == "assistant"
    assert messages[-1].content == "已经读取完毕"

    # 工具 schema 应该随请求一起发给模型
    assert client.requests


def test_agent_reports_llm_error():
    class BrokenClient(FakeClient):
        def stream(self, messages):
            raise RuntimeError("boom")
            yield  # pragma: no cover

    agent = Agent(client=BrokenClient([]), registry=ToolRegistry())
    events = list(agent.run("hi"))
    assert any(event.kind == "error" for event in events)


def test_agent_emits_delta_events():
    client = FakeClient([[LLMDelta(content="你"), LLMDelta(content="好")]])
    agent = Agent(client=client, registry=ToolRegistry())
    events = list(agent.run("hi"))
    deltas = [e.text for e in events if isinstance(e, AssistantDeltaEvent)]
    assert deltas == ["你", "好"]
    assert any(isinstance(e, AssistantMessageEvent) for e in events)
