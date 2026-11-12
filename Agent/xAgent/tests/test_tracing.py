# -*- coding: utf-8 -*-
"""调用追踪日志测试：JSON 行结构、脱敏、耗时与失败状态。"""

from __future__ import annotations

import io
import json
import logging
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import tracing  # noqa: E402
from core.tools.registry import ToolRegistry  # noqa: E402
from core.tools.base import FunctionTool  # noqa: E402


def _capture_logger() -> tuple:
    stream = io.StringIO()
    logger = logging.getLogger(tracing.LOGGER_NAME)
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(stream)
    handler.setFormatter(tracing.JsonLineFormatter())
    logger.addHandler(handler)
    return logger, stream


def test_tool_call_is_written_as_json_line():
    logger, stream = _capture_logger()
    registry = ToolRegistry(
        [
            FunctionTool(
                name="echoTool",
                description="回显输入",
                parameters={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
                func=lambda text: "echo:" + text,
            )
        ]
    )
    result = registry.execute("echoTool", json.dumps({"text": "hi"}))
    assert result.ok and result.output == "echo:hi"

    line = [ln for ln in stream.getvalue().splitlines() if ln.strip()][-1]
    payload = json.loads(line)
    assert payload["event"] == "tool_call"
    assert payload["tool_name"] == "echoTool"
    assert payload["status"] == "ok"
    assert isinstance(payload["duration_ms"], (int, float)) and payload["duration_ms"] >= 0


def test_failed_call_records_status():
    logger, stream = _capture_logger()
    registry = ToolRegistry()
    registry.execute("notExist", "{}")
    payload = json.loads(stream.getvalue().splitlines()[-1])
    assert payload["status"] == "unknown_tool"


def test_sensitive_fields_are_redacted():
    captured = []

    class _Handler(logging.Handler):
        def emit(self, record):
            captured.append(record.detail)

    logger = logging.getLogger(tracing.LOGGER_NAME)
    handler = _Handler()
    logger.addHandler(handler)
    tracing.record_tool_call(
        "Search", "ok", 12.5, {"arguments": {"api_key": "sk-real", "q": "x"}}
    )
    logger.removeHandler(handler)
    assert captured[-1]["arguments"]["api_key"] == "[REDACTED]"
    assert captured[-1]["arguments"]["q"] == "x"


def test_configure_writes_file_in_workspace():
    tracing._configured = False
    for handler in list(logging.getLogger(tracing.LOGGER_NAME).handlers):
        logging.getLogger(tracing.LOGGER_NAME).removeHandler(handler)

    tmp = Path(tempfile.mkdtemp(prefix="xagent_trace_"))
    tracing.configure(str(tmp))
    tracing.record_tool_call("getDate", "ok", 1.0, {"output": "2026-11-12"})
    log_file = Path(tracing.log_path(str(tmp)))
    assert log_file.exists()
    assert "getDate" in log_file.read_text(encoding="utf-8")
