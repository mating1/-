# -*- coding: utf-8 -*-
"""MCP 桥接层离线单元测试（不连接真实服务器）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.tools.mcp.service import MCPBridge  # noqa: E402


def test_load_reads_mcp_servers(tmp_path):
    (tmp_path / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"demo": {"url": "http://127.0.0.1:8000/mcp"}}}),
        encoding="utf-8",
    )
    config = MCPBridge._load(tmp_path)
    assert "demo" in config


def test_load_accepts_top_level_dict(tmp_path):
    (tmp_path / ".mcp.json").write_text(
        json.dumps({"demo": {"command": "npx"}}), encoding="utf-8"
    )
    config = MCPBridge._load(tmp_path)
    assert "demo" in config


def test_load_bad_json_returns_empty(tmp_path):
    (tmp_path / ".mcp.json").write_text("{not json", encoding="utf-8")
    assert MCPBridge._load(tmp_path) == {}


def test_normalize_gender_chinese_to_enum():
    assert MCPBridge._normalize_args({"gender": "男"})["gender"] == "male"
    assert MCPBridge._normalize_args({"gender": "女"})["gender"] == "female"
    assert MCPBridge._normalize_args({"gender": "male"})["gender"] == "male"
    # 数字性别（旧 Bazi）保持原样
    assert MCPBridge._normalize_args({"gender": 1})["gender"] == 1


def test_normalize_date_adds_time():
    args = MCPBridge._normalize_args({"date": "2026-11-11"})
    assert args["date"] == "2026-11-11T12:00"
    # 已是 ISO 时间不重复补
    args2 = MCPBridge._normalize_args({"date": "2026-11-11T09:30"})
    assert args2["date"] == "2026-11-11T09:30"


def test_normalize_keeps_other_args():
    args = MCPBridge._normalize_args({"question": "运势", "birthYear": 1995})
    assert args["question"] == "运势"
    assert args["birthYear"] == 1995
