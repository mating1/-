# -*- coding: utf-8 -*-
"""历史会话列表面板：上下键选择、回车恢复、ESC 取消。"""

from __future__ import annotations

from typing import Dict, List, Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option


class ResumeScreen(ModalScreen[Optional[str]]):
    """会话恢复弹窗，dismiss 返回被选中的 session id（取消时为 None）。"""

    BINDINGS = [("escape", "cancel", "取消")]

    def __init__(self, sessions: List[Dict]) -> None:
        super().__init__()
        self._sessions = sessions

    def compose(self) -> ComposeResult:
        with Vertical(id="resume-box"):
            yield Static(
                "历史会话（↑↓ 选择 · Enter 恢复 · Esc 取消）",
                id="resume-title",
                markup=False,
            )
            yield OptionList(id="resume-list")
            yield Static("共 %d 个会话存档" % len(self._sessions), id="resume-hint", markup=False)

    def on_mount(self) -> None:
        options = self.query_one(OptionList)
        for item in self._sessions:
            options.add_option(
                Option(
                    "%s  %s  %d 条" % (item.get("created", ""), item.get("title", ""), item.get("count", 0)),
                    id=str(item.get("id", "")),
                )
            )
        if self._sessions:
            options.highlighted = 0
        options.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(str(event.option.id))

    def action_cancel(self) -> None:
        self.dismiss(None)


__all__ = ["ResumeScreen"]
