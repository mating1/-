# -*- coding: utf-8 -*-
"""配置加载与兜底转换的单元测试。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import (  # noqa: E402
    DEFAULT_SYSTEM_PROMPT,
    _to_bool,
    _to_float,
    _to_int,
    load_config,
)

INI = """
[llm]
base_url = https://api.deepseek.com/v1
api_key = sk-test
model = deepseek-chat

[agent]
max_iterations = 8
workspace = .
"""


def test_default_prompt_is_xuanxue():
    assert "玄机真人" in DEFAULT_SYSTEM_PROMPT
    assert "玄学" in DEFAULT_SYSTEM_PROMPT


def test_to_float_fallback():
    assert _to_float(None, 1.5) == 1.5
    assert _to_float("abc", 2.0) == 2.0
    assert _to_float("3.25", 0.0) == 3.25


def test_to_int_fallback():
    assert _to_int(None, 8) == 8
    assert _to_int("x", 8) == 8
    assert _to_int("12", 0) == 12


def test_to_bool_fallback():
    assert _to_bool("true", False) is True
    assert _to_bool("0", True) is False
    assert _to_bool(None, True) is True
    assert _to_bool("maybe", False) is False


def test_load_config_defaults(tmp_path):
    ini = tmp_path / "config.ini"
    ini.write_text(INI, encoding="utf-8")
    cfg = load_config(str(ini))
    assert cfg.llm.model == "deepseek-chat"
    assert cfg.max_iterations == 8
    assert "玄机真人" in cfg.system_prompt
    assert cfg.mcp_connect_timeout == 30.0
    assert cfg.auto_save_session is True
