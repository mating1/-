# -*- coding: utf-8 -*-
"""配置加载。

配置来源优先级：环境变量 > config.ini 文件 > 代码内默认值。
环境变量便于在 CI / 容器 / 多环境部署时避免把密钥写进文件。

首次运行若找不到 config.ini，会自动在当前工作目录生成一份带 mock 值的
完整模板，并要求用户修改后重启（由 TUI 弹窗提示）。
"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple

from .errors import ConfigError

DEFAULT_CONFIG_NAME = "config.ini"

ENV_API_KEY = "XAGENT_API_KEY"
ENV_BASE_URL = "XAGENT_BASE_URL"
ENV_MODEL = "XAGENT_MODEL"

DEFAULT_SYSTEM_PROMPT = (
    "你是「玄机真人」，一位精通八字、紫微斗数、塔罗、西洋与吠陀占星、"
    "六爻、梅花易数、奇门遁甲、风水与数字命理的玄学命理顾问。主业是依据用户"
    "提供的生辰、问题或卦象做专业、温和的运势解读与择吉建议；先问清性别、"
    "出生年月日时（注明公历/农历、时辰）与所问之事，再结合对应技能或 MCP 排盘"
    "分析。文件读写、目录浏览、网页抓取、命令行、文档生成只是后台复用的辅助"
    "能力，仅在需要查阅资料、保存或生成命盘报告时才调用，不要主动罗列这些文件"
    "工具。回答简洁准确，命理措辞符合传统语境，不夸大吉凶、不制造恐慌。"
)

# 首次启动自动生成的配置模板（mock 值，需用户修改后重启）
CONFIG_TEMPLATE = """# xAgent 配置文件（首次启动自动生成）
# 请把 [llm] 段中的 base_url / api_key / model 改成你自己的有效配置，然后重新启动。
# 其余配置项都有默认值，可按需调整。

[llm]
base_url = https://api.deepseek.com/v1
api_key = sk-mock-000000000000000000000000
model = deepseek-chat
timeout = 60

[agent]
system_prompt = 你是「玄机真人」，一位精通八字、紫微斗数、塔罗、占星、六爻、梅花易数、奇门遁甲、风水与数字命理的玄学命理顾问。主业是依据生辰、问题或卦象做运势解读与择吉建议；先问清性别、出生年月日时（公历/农历、时辰）与所问之事，再结合技能或 MCP 排盘分析。文件读写、网页抓取、命令行、文档生成只是后台辅助能力，仅在查阅资料或生成命盘报告时调用，不要主动罗列文件工具。回答简洁准确，命理措辞符合传统语境，不夸大吉凶、不制造恐慌。
max_iterations = 8
workspace = .
context_window = 128000

[context]
# 触发压缩告警/封锁的阈值（占上下文窗口比例）
threshold = 0.7
# 上下文归档目录（相对工作区）
archive_dir = .agents/context
# recallContext 单次最多返回条数、单条截断字符数
recall_limit = 8
recall_snippet = 240

[voice]
# 本地离线语音识别模型（faster-whisper），首次使用会自动下载
model = small
device = cpu
compute_type = int8
language = zh

[session]
# 会话存档目录（相对工作区）
dir = .agents/sessions
# 退出/新建会话时是否自动保存
auto_save = true

[mcp]
# 连接 MCP Server 的等待超时（秒）
connect_timeout = 30
# 单次 MCP 工具调用超时（秒）
call_timeout = 120

[ui]
# 流式输出刷新间隔（秒）
stream_flush_interval = 0.06
# 项目约定文件名：存在时首次注入到会话历史
agents_file = AGENTS.md
"""


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
    context_window: int = 128000
    context_window_is_default: bool = True
    source_path: str = field(default="", repr=False)
    # 上下文压缩
    context_threshold: float = 0.7
    archive_dirname: str = ".agents/context"
    recall_limit: int = 8
    recall_snippet: int = 240
    # 语音
    voice_model: str = "small"
    voice_device: str = "cpu"
    voice_compute_type: str = "int8"
    voice_language: str = "zh"
    # 会话存档
    session_dirname: str = ".agents/sessions"
    auto_save_session: bool = True
    # MCP
    mcp_connect_timeout: float = 30.0
    mcp_call_timeout: float = 120.0
    # 界面
    stream_flush_interval: float = 0.06
    agents_filename: str = "AGENTS.md"
    # 本次是否是首次生成配置（需提示用户修改后重启）
    config_created: bool = False

    @property
    def workdir(self) -> Path:
        return Path(self.workspace).expanduser().resolve()

    @property
    def archive_path(self) -> Path:
        return self.workdir / self.archive_dirname

    @property
    def session_path(self) -> Path:
        return self.workdir / self.session_dirname


def resolve_config_path(explicit: Optional[str] = None) -> Tuple[Path, bool]:
    """定位 config.ini，返回 (路径, 是否为本次新建)。

    查找顺序：显式路径 > 环境变量 > 当前工作目录；
    都没有时在当前工作目录生成一份 mock 模板。
    """
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise ConfigError("配置文件不存在：%s" % path)
        return path, False

    env_path = os.environ.get("XAGENT_CONFIG")
    if env_path:
        path = Path(env_path).expanduser()
        if not path.is_file():
            raise ConfigError("XAGENT_CONFIG 指向的配置文件不存在：%s" % path)
        return path, False

    cwd_config = Path.cwd() / DEFAULT_CONFIG_NAME
    if cwd_config.is_file():
        return cwd_config, False

    write_config_template(cwd_config)
    return cwd_config, True


def write_config_template(path: Path) -> Path:
    """写出一份带 mock 值的完整配置模板。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(CONFIG_TEMPLATE, encoding="utf-8")
    return path


def find_config_path(explicit: Optional[str] = None) -> Path:
    """兼容旧接口：只返回配置文件路径。"""
    return resolve_config_path(explicit)[0]


def load_config(path: Optional[str] = None) -> AppConfig:
    """读取配置并返回不可变的配置对象；缺文件时自动生成模板。"""
    config_path, created = resolve_config_path(path)
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

    context_window_raw = str(agent_section.get("context_window", "")).strip()
    context_window = _to_int(context_window_raw, 0) if context_window_raw else 0
    if context_window > 0:
        context_window_is_default = False
    else:
        context_window = 128000
        context_window_is_default = True

    context_section = parser["context"] if parser.has_section("context") else {}
    threshold = _to_float(context_section.get("threshold"), 0.7)
    archive_dirname = (context_section.get("archive_dir") or ".agents/context").strip()
    recall_limit = _to_int(context_section.get("recall_limit"), 8)
    recall_snippet = _to_int(context_section.get("recall_snippet"), 240)

    voice_section = parser["voice"] if parser.has_section("voice") else {}
    voice_model = (voice_section.get("model") or "small").strip()
    voice_device = (voice_section.get("device") or "cpu").strip()
    voice_compute_type = (voice_section.get("compute_type") or "int8").strip()
    voice_language = (voice_section.get("language") or "zh").strip()

    session_section = parser["session"] if parser.has_section("session") else {}
    session_dirname = (session_section.get("dir") or ".agents/sessions").strip()
    auto_save_session = _to_bool(session_section.get("auto_save"), True)

    mcp_section = parser["mcp"] if parser.has_section("mcp") else {}
    mcp_connect_timeout = _to_float(mcp_section.get("connect_timeout"), 30.0)
    mcp_call_timeout = _to_float(mcp_section.get("call_timeout"), 120.0)

    ui_section = parser["ui"] if parser.has_section("ui") else {}
    stream_flush_interval = _to_float(ui_section.get("stream_flush_interval"), 0.06)
    agents_filename = (ui_section.get("agents_file") or "AGENTS.md").strip()

    return AppConfig(
        llm=LLMConfig(base_url=base_url, api_key=api_key, model=model, timeout=timeout),
        system_prompt=system_prompt or DEFAULT_SYSTEM_PROMPT,
        max_iterations=max_iterations,
        workspace=workspace,
        context_window=context_window,
        context_window_is_default=context_window_is_default,
        source_path=str(config_path),
        context_threshold=threshold,
        archive_dirname=archive_dirname,
        recall_limit=recall_limit,
        recall_snippet=recall_snippet,
        voice_model=voice_model,
        voice_device=voice_device,
        voice_compute_type=voice_compute_type,
        voice_language=voice_language,
        session_dirname=session_dirname,
        auto_save_session=auto_save_session,
        mcp_connect_timeout=mcp_connect_timeout,
        mcp_call_timeout=mcp_call_timeout,
        stream_flush_interval=stream_flush_interval,
        agents_filename=agents_filename,
        config_created=created,
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


def _to_bool(raw, default: bool) -> bool:
    if raw is None:
        return default
    value = str(raw).strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    return default
