# -*- coding: utf-8 -*-
"""上下文压缩日志浮动面板。

压缩完成后弹出：左栏显示压缩前原文，右栏显示压缩后结果，
两栏各自可滚动，底部有关闭按钮。
"""

from __future__ import annotations

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class CompactLogScreen(ModalScreen):
    """压缩前后对照的浮动面板。"""

    def __init__(self, before: str, after: str) -> None:
        super().__init__()
        self._before = before or "（无内容）"
        self._after = after or "（无内容）"

    def compose(self):
        yield Static("🗜 上下文压缩日志 ｜ 左：压缩前原文 · 右：压缩后结果", id="compact-log-title")
        yield Horizontal(
            Vertical(
                Static("压缩前原文", classes="compact-col-title"),
                VerticalScroll(Static(self._before, markup=False, classes="compact-body"), id="compact-scroll-before"),
                classes="compact-col",
            ),
            Vertical(
                Static("压缩后结果", classes="compact-col-title"),
                VerticalScroll(Static(self._after, markup=False, classes="compact-body"), id="compact-scroll-after"),
                classes="compact-col",
            ),
            id="compact-cols",
        )
        yield Button("关闭", id="compact-log-close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "compact-log-close":
            self.dismiss()
