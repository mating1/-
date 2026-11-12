# -*- coding: utf-8 -*-
"""TUI（终端用户界面）前端。

这一层只负责"展示"和"采集输入"：
- 输入 -> core.Agent
- core.Agent 的事件 -> 界面

未来新增 web / desktop / mobile 前端时，core 层完全不需要改动。
"""

from .app import XAgentApp, run_tui

__all__ = ["XAgentApp", "run_tui"]
