# -*- coding: utf-8 -*-
"""配置加载。

配置来源优先级：环境变量 > config.ini 文件 > 代码内默认值。
环境变量便于在 CI / 容器 / 多环境部署时避免把密钥写进文件。
"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .errors import ConfigError

DEFAULT_CONFIG_NAME = "config.ini"

ENV_API_KEY = "XAGENT_API_KEY"
ENV_BASE_URL = "XAGENT_BASE_URL"
ENV_MODEL = "XAGENT_MODEL"

DEFAULT_SYSTEM_PROMPT = (
    "你是一个运行在命令行里的文件操作助手，"
    "可以使用提供的文件工具查看目录、读取文件、创建和修改文件。"
    "回答要简洁准确，涉及文件操作时先说明将要做什么。"
)


@dataclass(frozen=True)
class LLMConfig:
    """大模型接口配置。"""

    base_url: str
    api_key: str
    model: str
    timeout: float = 60.0

    @property
    def endpoint(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"


@dataclass(frozen=True)
class AppConfig:
    """应用级配置。"""

    llm: LLMConfig
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    max_iterations: int = 8
    workspace: str = "."
    source_path: str = field(default="", repr=False)

    @property
    def workdir(self) -> Path:
        return Path(self.workspace).expanduser().resolve()


def find_config_path(explicit: Optional[str] = None) -> Path:
    """定位 config.ini：显式路径 > 环境变量 > 包根目录。"""
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise ConfigError("配置文件不存在：%s" % path)
        return path

    env_path = os.environ.get("XAGENT_CONFIG")
    if env_path:
        path = Path(env_path).expanduser()
        if not path.is_file():
            raise ConfigError("XAGENT_CONFIG 指向的配置文件不存在：%s" % path)
        return path

    return Path(__file__).resolve().parent.parent / DEFAULT_CONFIG_NAME


def load_config(path: Optional[str] = None) -> AppConfig:
    """读取配置并返回不可变的配置对象。"""
    config_path = find_config_path(path)
    parser = configparser.ConfigParser()
    try:
        parser.read(config_path, encoding="utf-8")
    except configparser.Error as exc:
        raise ConfigError("配置文件解析失败：%s" % exc) from exc

    if not parser.has_section("llm"):
        raise ConfigError("配置文件缺少 [llm] 段：%s" % config_path)

    llm_section = parser["llm"]
    base_url = (os.environ.get(ENV_BASE_URL) or llm_section.get("base_url", "")).strip()
    api_key = (os.environ.get(ENV_API_KEY) or llm_section.get("api_key", "")).strip()
    model = (os.environ.get(ENV_MODEL) or llm_section.get("model", "")).strip()

    missing = [
        name
        for name, value in (("base_url", base_url), ("api_key", api_key), ("model", model))
        if not value
    ]
    if missing:
        raise ConfigError(
            "配置项缺失：%s（可在 %s 中配置或设置环境变量）" % (", ".join(missing), ENV_API_KEY)
        )

    timeout = _to_float(llm_section.get("timeout"), 60.0)

    agent_section = parser["agent"] if parser.has_section("agent") else {}
    system_prompt = agent_section.get("system_prompt", DEFAULT_SYSTEM_PROMPT).strip()
    max_iterations = _to_int(agent_section.get("max_iterations"), 8)
    workspace = agent_section.get("workspace", ".").strip() or "."

    return AppConfig(
        llm=LLMConfig(base_url=base_url, api_key=api_key, model=model, timeout=timeout),
        system_prompt=system_prompt or DEFAULT_SYSTEM_PROMPT,
        max_iterations=max_iterations,
        workspace=workspace,
        source_path=str(config_path),
    )


def _to_float(raw, default: float) -> float:
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _to_int(raw, default: int) -> int:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default
