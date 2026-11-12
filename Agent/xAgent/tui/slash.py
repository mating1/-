# -*- coding: utf-8 -*-
"""斜杠命令定义与补全提示面板。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from textual.widgets import Static


@dataclass(frozen=True)
class SlashCommand:
    """一条斜杠命令的元信息。"""

    name: str
    description: str


SLASH_COMMANDS: List[SlashCommand] = [
    SlashCommand("/help", "显示全部斜杠命令"),
    SlashCommand("/new", "新建会话（自动保存当前历史）"),
    SlashCommand("/resume", "列出历史会话并恢复"),
    SlashCommand("/save", "保存当前会话"),
    SlashCommand("/title", "给本次会话起名字（/title 名称）"),
    SlashCommand("/compact", "压缩当前上下文"),
    SlashCommand("/clear", "清空当前上下文"),
    SlashCommand("/skills", "列出已加载的 Skill"),
    SlashCommand("/mcp", "查看 MCP 服务器与工具状态"),
    SlashCommand("/config", "查看配置文件与模型"),
    SlashCommand("/quit", "退出程序"),
]

COMMAND_NAMES = tuple(c.name for c in SLASH_COMMANDS)


def matching_commands(prefix: str) -> List[SlashCommand]:
    """按前缀过滤命令；输入已含空格时不再提示。"""
    text = (prefix or "").strip()
    if not text.startswith("/") or " " in text:
        return []
    return [c for c in SLASH_COMMANDS if c.name.startswith(text)] or list(SLASH_COMMANDS)


def help_text() -> str:
    """全部命令的展示文本。"""
    lines = ["可用命令："]
    for command in SLASH_COMMANDS:
        lines.append("  %-10s %s" % (command.name, command.description))
    return "\n".join(lines)


class SlashHint(Static):
    """输入框上方的补全引导面板：边打字边列出匹配命令。"""

    def __init__(self) -> None:
        super().__init__("", markup=False, id="slash-hint")
        self.display = False

    def refresh_for(self, value: str) -> None:
        commands = matching_commands(value)
        if not commands:
            self.display = False
            return
        self.update("\n".join("%-10s %s" % (c.name, c.description) for c in commands))
        self.display = True


__all__ = ["SlashCommand", "SlashHint", "SLASH_COMMANDS", "help_text", "matching_commands"]
