# -*- coding: utf-8 -*-
"""首次生成配置文件后的提示弹窗。"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ConfigWarningScreen(ModalScreen[None]):
    """告诉用户已生成 mock 配置，需要修改后重新启动。"""

    BINDINGS = [
        ("escape", "close", "关闭"),
        ("enter", "close", "关闭"),
    ]

    def __init__(self, config_path: str) -> None:
        super().__init__()
        self._config_path = config_path

    def compose(self) -> ComposeResult:
        with Vertical(id="config-warn-box"):
            yield Static("已生成新的配置文件", id="config-warn-title", markup=False)
            yield Static(
                "当前目录没有 config.ini，已自动生成一份带 mock 值的完整配置：\n\n"
                "  %s\n\n"
                "请把 [llm] 段的 base_url / api_key / model 改成真实可用的值，"
                "然后重新启动程序才能正常工作。"
                % self._config_path,
                id="config-warn-body",
                markup=False,
            )
            yield Button("我已了解", id="config-warn-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "config-warn-close":
            self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)


__all__ = ["ConfigWarningScreen"]
