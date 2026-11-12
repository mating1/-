# -*- coding: utf-8 -*-
"""TUI 专用控件。

控件只负责渲染，不含任何业务逻辑；数据全部来自 core 层的事件对象。
"""

from __future__ import annotations

import json
from typing import Optional

from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Collapsible, ListItem, ListView, Static
from textual import on

from core.models import ToolCall, ToolExecution


class UserBubble(Static):
    """用户消息气泡。"""

    def __init__(self, text: str) -> None:
        super().__init__(text, markup=False, classes="user-bubble")


class ErrorBanner(Static):
    """错误提示条。"""

    def __init__(self, message: str) -> None:
        super().__init__("⚠ %s" % message, markup=False, classes="error-banner")


class CollapseBar(Static):
    """细窄的收起条：一行高，点一下收起对应面板。"""

    class Pressed(Message):
        def __init__(self, target: str) -> None:
            super().__init__()
            self.target = target

    def __init__(self, target: str, label: str) -> None:
        super().__init__(label, markup=False, id="collapse-" + target, classes="collapse-bar")
        self._target = target

    def on_click(self, event) -> None:
        self.post_message(self.Pressed(self._target))
        event.stop()


class Sidebar(Vertical):
    """左侧栏：工作区说明 + MCP 状态 + 历史会话，可整体收起。"""

    class SessionSelected(Message):
        """用户点选了某个历史会话。"""

        def __init__(self, session_id: str) -> None:
            super().__init__()
            self.session_id = session_id

    def __init__(self, info: str = "", mcp_info: str = "") -> None:
        super().__init__(id="sidebar")
        self._info = Static(info or "", markup=False, classes="side-info")
        self._mcp_title = Static("MCP 服务器", classes="side-title")
        self._mcp_info = Static(
            mcp_info or "加载中…", markup=False, classes="side-info mcp-info"
        )
        self._session_ids = {}

    def compose(self):
        with VerticalScroll(id="sidebar-scroll"):
            yield CollapseBar("sidebar", "▴ 收起工作区")
            yield Static("工作区", classes="side-title")
            yield self._info
            yield self._mcp_title
            yield self._mcp_info
            yield Static("历史会话", classes="side-title")
            yield ListView(id="session-list")

    def set_mcp(self, text: str) -> None:
        self._mcp_info.update(text)

    def set_sessions(self, entries) -> None:
        try:
            listing = self.query_one("#session-list", ListView)
        except Exception:  # noqa: BLE001
            return
        listing.clear()
        self._session_ids = {}
        for entry in list(entries)[:10]:
            created = str(entry.get("created") or "")[5:16]
            label = "%s  %s" % (created, entry.get("title") or "未命名")
            item = ListItem(Static(label, markup=False))
            self._session_ids[id(item)] = str(entry.get("id") or "")
            listing.append(item)

    @on(ListView.Selected, "#session-list")
    def _pick_session(self, event) -> None:
        session_id = self._session_ids.get(id(event.item))
        if session_id:
            self.post_message(self.SessionSelected(session_id))


class Splitter(Static):
    """可拖动的分隔条：拖动改变相邻面板宽度。"""

    def __init__(self, target_id: str, invert: bool = False, min_width: int = 8,
                 max_width: int = 110) -> None:
        super().__init__("┃", id="grip-" + target_id.lstrip("#"), classes="splitter")
        self._target_id = target_id
        self._invert = invert
        self._min_width = min_width
        self._max_width = max_width
        self._start_x = 0
        self._start_width = 0
        self._dragging = False

    def on_mouse_down(self, event) -> None:
        self._start_x = getattr(event, "screen_x", event.x)
        try:
            # 目标面板处于收起状态时，拖动前先把它展开
            target = self.app.query_one(self._target_id)
            was_hidden = not target.display
            self.app.ensure_visible(self._target_id)
            self._start_width = 28 if was_hidden else target.size.width
        except Exception:  # noqa: BLE001
            return
        self._dragging = True
        try:
            self.capture_mouse()
        except Exception:  # noqa: BLE001
            pass
        event.stop()

    def on_mouse_move(self, event) -> None:
        if not self._dragging:
            return
        try:
            current = getattr(event, "screen_x", event.x)
            delta = current - self._start_x
            if self._invert:
                delta = -delta
            width = max(self._min_width, min(self._max_width, self._start_width + delta))
            self.app.query_one(self._target_id).styles.width = width
        except Exception:  # noqa: BLE001
            pass
        event.stop()

    def on_mouse_up(self, event) -> None:
        if self._dragging:
            self._dragging = False
            try:
                self.release_mouse()
            except Exception:  # noqa: BLE001
                pass
        event.stop()


class FilePanel(Vertical):
    """右侧栏：列出会话中生成/编辑的文件，点击查看内容，右键收起。"""

    def __init__(self, on_open) -> None:
        self._on_open = on_open
        self._paths = {}
        self._by_item = {}
        super().__init__(id="file-panel")

    def compose(self):
        yield CollapseBar("file-panel", "▴ 收起文件区")
        yield Static("生成的文件", classes="side-title")
        yield ListView(id="file-list")

    def _on_mouse_down(self, event) -> None:
        if getattr(event, "button", 0) == 2:  # 右键
            self.display = False
            event.stop()

    def add_file(self, path: str) -> None:
        if not path or path in self._paths:
            return
        item = ListItem(Static(path.split("\\")[-1], markup=False))
        self._paths[path] = item
        self._by_item[id(item)] = path
        self.query_one("#file-list", ListView).append(item)

    @on(ListView.Selected)
    def _selected(self, event) -> None:
        item = event.item
        path = self._by_item.get(id(item), "")
        if path:
            self._on_open(path)


class ToolCallCard(Collapsible):
    """工具调用卡片：折叠状态下显示工具名，展开后显示参数与结果。"""

    def __init__(self, call: ToolCall) -> None:
        self.call = call
        self._body = Static(self._format_arguments(call), markup=False, classes="tool-body")
        super().__init__(
            self._body,
            title="🔧 %s" % (call.name or "unknown"),
            collapsed=True,
            classes="tool-card",
        )

    def set_result(self, execution: Optional[ToolExecution]) -> None:
        """写入工具执行结果。"""
        if execution is None:
            return
        status = "成功" if execution.ok else "失败"
        self._body.update(
            "%s\n\n─── 结果（%s）───\n%s"
            % (self._format_arguments(self.call), status, execution.output or "（无输出）")
        )

    @staticmethod
    def _format_arguments(call: ToolCall) -> str:
        raw = call.arguments or "{}"
        try:
            pretty = json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
        except (ValueError, TypeError):
            pretty = raw
        return "─── 参数 ───\n%s" % pretty


class StatusBar(Static):
    """底部状态栏。"""

    def __init__(self) -> None:
        super().__init__("", markup=False, id="status-bar", classes="status-bar")
