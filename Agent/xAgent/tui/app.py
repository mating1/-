# -*- coding: utf-8 -*-
"""Textual 终端界面。

职责：渲染 core 层的事件、采集用户输入。
本文件不出现任何业务规则——所有工具调用与模型交互都在 core 中完成。
"""

from __future__ import annotations

import sys
import threading
import time
from typing import Dict, Optional

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Footer, Header, Input, Markdown, Static

from core.agent import Agent
from core.config import AppConfig, load_config
from core.events import (
    AssistantDeltaEvent,
    AssistantMessageEvent,
    CompactFailedEvent,
    CompactFinishedEvent,
    CompactStartedEvent,
    ContextUsageEvent,
    ErrorEvent,
    ToolCallFinishedEvent,
    ToolCallStartedEvent,
    TurnCompletedEvent,
    UserMessageEvent,
)
from core.factory import build_agent

from .compact_log import CompactLogScreen
from .config_warning import ConfigWarningScreen
from .pet import Pet, SpeechBubble
from .resume import ResumeScreen
from .slash import SlashHint, help_text

if sys.platform == "win32":
    from .win_byte_driver import WindowsByteDriver
from .widgets import (
    CollapseBar,
    ErrorBanner,
    FilePanel,
    Sidebar,
    Splitter,
    StatusBar,
    ToolCallCard,
    UserBubble,
)

DEFAULT_STREAM_FLUSH_INTERVAL = 0.06

# 语音按钮图标：空闲是樱花话筒，录音是樱花红点，识别中是呼吸的三点
VOICE_IDLE = "🌸🎤"
VOICE_RECORDING = "🌸●"


class XAgentApp(App):
    """xAgent 的终端界面。"""

    CSS_PATH = "style.tcss"
    TITLE = "玄机真人"
    SUB_TITLE = "玄学命理助手 · TUI"

    BINDINGS = [
        Binding("ctrl+l", "clear_chat", "清空上下文"),
        Binding("ctrl+n", "new_session", "新建会话"),
        Binding("ctrl+q", "quit", "退出"),
    ]

    def get_driver_class(self):
        # Windows/ConPTY 下自带 WindowsDriver 读不到鼠标 SGR，改用字节流驱动。
        if sys.platform == "win32":
            return WindowsByteDriver
        return super().get_driver_class()

    def __init__(self, agent: Agent, config: AppConfig) -> None:
        super().__init__()
        self.theme = "textual-light"
        self.agent = agent
        self.config = config
        self._busy = False
        self._streaming: Optional[Markdown] = None
        self._stream_buffer = ""
        self._last_flush = 0.0
        self._cards: Dict[str, ToolCallCard] = {}
        self._sidebar_visible = True
        self._files_visible = True
        self._warned = False
        self._recording = False
        self._stop_flag: Optional[threading.Event] = None
        self._dots_timer = None
        self._dots_index = 0
        self._whisper = None
        self._cc = None
        self._mcp_status: dict = {"available": False, "servers": {}, "tool_count": 0}

    # ------------------------------------------------------------------
    # 布局
    # ------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Horizontal(
            Vertical(
                Button("☰ 工作区", id="btn-sidebar"),
                Button("＋ 新会话", id="btn-new"),
                Button("🗂 会话", id="btn-resume"),
                Button("🧹 清空", id="btn-clear"),
                Button("📁 文件", id="btn-files"),
                id="toolbar",
            ),
            Splitter("#toolbar", min_width=6, max_width=60),
            Sidebar(),
            VerticalScroll(id="chat-log"),
            Splitter("#file-panel", invert=True),
            FilePanel(self._open_file),
            id="main-row",
        )
        yield StatusBar()
        yield SlashHint()
        yield Horizontal(
            Input(
                placeholder="请输入问题，Enter 发送 · Ctrl+L 清空上下文 · Ctrl+N 新会话",
                id="prompt",
            ),
            Button(VOICE_IDLE, id="btn-voice"),
            id="prompt-row",
        )
        yield Footer()
        yield Pet()
        yield SpeechBubble()

    async def on_resize(self, event) -> None:
        # 兜底：同步驱动缓存的终端尺寸，避免残留旧宽高导致布局按旧尺寸计算。
        if self._driver is not None:
            self._driver._size = (event.size.width, event.size.height)

    async def on_mount(self) -> None:
        self.query_one("#prompt", Input).focus()
        # 吉祥物初始停在右上角，之后由用户自己拖
        try:
            pet = self.query_one(Pet)
            pet.styles.offset = (max(2, self.size.width - 46), 3)
        except Exception:  # noqa: BLE001
            pass
        # 工作区侧栏默认收起，点工具栏“工作区”再展开
        self.query_one("#sidebar").display = False
        self._sidebar_visible = False
        info = "模型：%s\n工作目录：%s\n工具：%s" % (
            self.config.llm.model,
            self.config.workdir,
            "、".join(self.agent.registry.names),
        )
        sidebar = self.query_one(Sidebar)
        sidebar._info.update(info)
        sidebar.set_mcp(self._format_mcp({"available": False, "servers": {}, "tool_count": 0}, loading=True))
        self._refresh_status()
        await self._show_welcome()

        if self.config.config_created:
            self.push_screen(ConfigWarningScreen(self.config.source_path))

        # 某个 MCP Server 连上/失败时即时刷新边栏（迟到连上的也能补进工具列表）
        bridge = getattr(self.agent, "mcp_bridge", None)
        if bridge is not None and hasattr(bridge, "set_on_change"):
            bridge.set_on_change(self._on_mcp_change)

        # MCP 异步加载：先让界面可用，连上后再刷新边栏与工具列表
        self.run_worker(self._load_mcp_async, thread=True, group="mcp")

        # 历史会话列表（侧栏展开即可见）
        self._refresh_sessions()

    # ------------------------------------------------------------------
    # MCP 异步加载
    # ------------------------------------------------------------------
    def _load_mcp_async(self) -> None:
        try:
            status = self.agent.load_mcp()
        except Exception as exc:  # noqa: BLE001
            status = {"available": False, "servers": {}, "tool_count": 0, "error": str(exc)}
        self.call_from_thread(self._apply_mcp_status, status)

    def _apply_mcp_status(self, status: dict, schedule: bool = True) -> None:
        self._mcp_status = status
        try:
            self.query_one(Sidebar).set_mcp(self._format_mcp(status))
        except Exception:  # noqa: BLE001
            pass
        self._refresh_status()
        if schedule and status.get("tool_count"):
            self.notify("MCP 已就绪：%d 个工具" % status["tool_count"])
        if schedule and status.get("available"):
            # 冷启动较慢的 Server（如 npx 拉起的 Bazi）可能晚于首轮超时，
            # 这里再补两次同步，连上后刷新边栏与工具列表
            self.set_timer(5.0, self._resync_mcp)
            self.set_timer(20.0, self._resync_mcp)

    def _resync_mcp(self) -> None:
        self.run_worker(self._resync_mcp_worker, thread=True, group="mcp-resync")

    def _on_mcp_change(self) -> None:
        """MCP 连接线程回调：切到界面线程后补注册工具并刷新边栏。"""
        try:
            self.call_from_thread(self._mcp_changed)
        except Exception:  # noqa: BLE001 - 界面已关闭时忽略
            pass

    def _mcp_changed(self) -> None:
        self.run_worker(self._resync_mcp_worker, thread=True, group="mcp-resync")

    def _resync_mcp_worker(self) -> None:
        try:
            status = self.agent.load_mcp()
        except Exception:  # noqa: BLE001
            return
        self.call_from_thread(self._apply_mcp_status, status, False)

    @staticmethod
    def _format_mcp(status: dict, loading: bool = False) -> str:
        if loading:
            return "加载中…（不阻塞界面）"
        if not status.get("available"):
            return "未找到 .mcp.json，未接入 MCP"
        servers = status.get("servers") or {}
        if not servers:
            return "没有配置 MCP 服务器"
        connected = sum(1 for s in servers.values() if s.get("connected"))
        lines = [
            "已连接 %d/%d 个服务器 · 工具 %d 个"
            % (connected, len(servers), status.get("tool_count", 0))
        ]
        for name, info in servers.items():
            mark = "✓" if info.get("connected") else "✗"
            tools = info.get("tools") or []
            lines.append("%s %s（%d）" % (mark, name, len(tools)))
            shown = tools[:6]
            for tool in shown:
                lines.append("   - %s" % tool)
            if len(tools) > len(shown):
                lines.append("   … 另有 %d 个" % (len(tools) - len(shown)))
            error = info.get("error") or ""
            if error:
                lines.append("   失败：%s" % " ".join(str(error).split())[:80])
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 输入
    # ------------------------------------------------------------------
    @on(Input.Submitted, "#prompt")
    async def _on_prompt_submitted(self, event: Input.Submitted) -> None:
        prompt = (event.value or "").strip()
        if not prompt:
            return
        event.input.value = ""
        self.query_one(SlashHint).display = False
        if prompt.startswith("/"):
            await self._handle_slash(prompt)
            return
        if self.agent.context_limit_reached():
            self.notify(
                "上下文已超过窗口 70%，请先执行 /compact 压缩上下文",
                severity="error",
            )
            return
        self._start_turn(prompt)

    @on(Input.Changed, "#prompt")
    def _on_prompt_changed(self, event: Input.Changed) -> None:
        """输入以 / 开头时，实时弹出命令补全引导面板。"""
        try:
            self.query_one(SlashHint).refresh_for(event.value or "")
        except Exception:  # noqa: BLE001
            pass

    async def _handle_slash(self, prompt: str) -> None:
        name = prompt.split()[0].lower()
        if name == "/help":
            await self._mount(Markdown("```text\n%s\n```" % help_text()))
        elif name == "/new":
            await self._do_new_session()
        elif name == "/resume":
            self._open_resume()
        elif name == "/save":
            self._do_save_session()
        elif name == "/title":
            parts = prompt.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                self.notify("用法：/title 会话名称", severity="warning")
            else:
                self.agent.set_session_title(parts[1].strip())
                self.notify("本次会话名称：%s" % self.agent.session_title)
        elif name == "/compact":
            self._start_compact()
        elif name == "/clear":
            await self.action_clear_chat()
        elif name == "/skills":
            await self._show_skills()
        elif name == "/mcp":
            await self._show_mcp()
        elif name == "/config":
            await self._show_config()
        elif name == "/quit":
            self.exit()
        else:
            self.notify("未知命令：%s（输入 /help 查看全部）" % name, severity="warning")

    async def _do_new_session(self) -> None:
        messages = list(self.agent.history)
        saved = self.agent.new_session(auto_save=self.config.auto_save_session)
        chat = self.query_one("#chat-log", VerticalScroll)
        await chat.remove_children()
        self._cards.clear()
        self._streaming = None
        self._stream_buffer = ""
        await self._show_welcome()
        self._refresh_status()
        if saved:
            self.notify("已保存上一会话：%s" % saved.name)
            self._name_session_later(saved, messages)
        else:
            self.notify("已新建会话")
        self._refresh_sessions()

    def _name_session_later(self, path, messages) -> None:
        """后台用模型给刚结束的会话总结一个名字。"""

        def work() -> None:
            try:
                title = self._summarize_title(messages)
            except Exception as exc:  # noqa: BLE001
                self._voice_log("会话命名失败：%r" % exc)
                return
            if not title:
                return
            try:
                self.agent.session_store.set_title(path, title)
            except Exception:  # noqa: BLE001
                return
            self.call_from_thread(self._refresh_sessions)

        self.run_worker(work, thread=True, group="title")

    def _summarize_title(self, messages) -> str:
        from core.llm.client import LLMClient
        from core.models import Message as ModelMessage

        lines = []
        for message in messages[:16]:
            if message.name == self.agent.agents_file:
                continue
            if message.role in ("user", "assistant") and message.content.strip():
                lines.append("%s：%s" % (message.role, message.content.strip()[:240]))
        transcript = "\n".join(lines)[:2400]
        if not transcript:
            return ""
        client = LLMClient(self.config.llm)
        prompt = (
            "请为下面这段对话起一个简短标题：不超过 12 个汉字，只输出标题本身，"
            "不要引号、不要标点、不要解释。\n\n" + transcript
        )
        chunks = []
        for delta in client.stream([ModelMessage(role="user", content=prompt)]):
            if delta.content:
                chunks.append(delta.content)
        title = "".join(chunks).strip()
        title = title.strip("「」《》\"'`").replace("\n", " ")
        return " ".join(title.split())[:20]

    def _do_save_session(self) -> None:
        try:
            path = self.agent.save_session()
        except Exception as exc:  # noqa: BLE001
            self.notify("保存失败：%s" % exc, severity="error")
            return
        if path is None:
            self.notify("当前未启用会话存档", severity="warning")
        else:
            self.notify("已保存会话：%s" % path.name)

    def _open_resume(self) -> None:
        store = self.agent.session_store
        if store is None:
            self.notify("当前未启用会话存档", severity="warning")
            return
        sessions = store.list()
        if not sessions:
            self.notify("还没有历史会话存档", severity="warning")
            return
        self.push_screen(ResumeScreen(sessions), self._after_resume)

    def on_unmount(self) -> None:
        """退出时把当前会话存档，避免历史丢失。"""
        if not getattr(self.config, "auto_save_session", True):
            return
        if not self.agent.history:
            return
        try:
            self.agent.save_session()
        except Exception:  # noqa: BLE001
            pass

    def _refresh_sessions(self) -> None:
        """把历史会话列表塞进侧栏。"""
        store = self.agent.session_store
        if store is None:
            return
        try:
            entries = store.list()
        except Exception:  # noqa: BLE001
            return
        try:
            self.query_one(Sidebar).set_sessions(entries)
        except Exception:  # noqa: BLE001
            pass

    def _after_resume(self, session_id) -> None:
        if not session_id:
            return
        try:
            self.agent.restore_session(str(session_id))
        except Exception as exc:  # noqa: BLE001
            self.notify("恢复会话失败：%s" % exc, severity="error")
            return
        self.run_worker(self._reload_chat(), group="reload")

    async def _reload_chat(self) -> None:
        chat = self.query_one("#chat-log", VerticalScroll)
        await chat.remove_children()
        self._cards.clear()
        self._streaming = None
        for message in self.agent.history:
            if message.name == self.agent.agents_file:
                await self._mount(Markdown("_已注入项目约定 %s_" % self.agent.agents_file))
                continue
            if message.role == "user" and message.content:
                await self._mount(UserBubble(message.content))
            elif message.role == "assistant" and message.content:
                await self._mount(Markdown(message.content))
        self._refresh_status()
        self.notify("已恢复会话，共 %d 条历史" % len(self.agent.history))

    async def _show_skills(self) -> None:
        from core.skills import discover_skills

        try:
            skills = discover_skills(self.config.workspace)
        except Exception as exc:  # noqa: BLE001
            self.notify("读取 Skill 失败：%s" % exc, severity="error")
            return
        if not skills:
            await self._mount(Static("当前项目没有发现 Skill（.agents/skills/）", markup=False))
            return
        lines = ["已加载 %d 个 Skill：" % len(skills)]
        for s in skills:
            desc = " ".join(s.description.split())
            if len(desc) > 36:
                desc = desc[:36] + "…"
            lines.append("· %s：%s" % (s.name, desc))
        await self._mount(Static("\n".join(lines), markup=False))
        self.query_one("#prompt", Input).focus()
    async def _show_mcp(self) -> None:
        await self._mount(
            Markdown("**MCP 服务器**\n\n```text\n%s\n```" % self._format_mcp(self._mcp_status))
        )

    async def _show_config(self) -> None:
        text = (
            "- 配置文件：`%s`\n"
            "- 模型：`%s`\n"
            "- 工作目录：`%s`\n"
            "- 上下文窗口：%d（%s）\n"
            "- 压缩阈值：%.0f%%\n"
            "- 会话存档：`%s`\n"
            "- MCP 连接超时：%.0fs · 调用超时：%.0fs\n"
            % (
                self.config.source_path,
                self.config.llm.model,
                self.config.workdir,
                self.config.context_window,
                "默认" if self.config.context_window_is_default else "配置值",
                self.config.context_threshold * 100,
                self.config.session_path,
                self.config.mcp_connect_timeout,
                self.config.mcp_call_timeout,
            )
        )
        await self._mount(Markdown("**配置信息**\n\n" + text))

    # ------------------------------------------------------------------
    # 动作
    # ------------------------------------------------------------------
    async def action_clear_chat(self) -> None:
        """清空界面与对话上下文。"""
        self.agent.reset()
        await self.query_one("#chat-log", VerticalScroll).remove_children()
        self._cards.clear()
        self._streaming = None
        await self._show_welcome()
        self._refresh_status()

    async def action_new_session(self) -> None:
        """新建会话（先自动保存当前历史）。"""
        await self._do_new_session()

    # ------------------------------------------------------------------
    # 工具栏
    # ------------------------------------------------------------------
    def _toggle(self, panel_id: str, attr: str) -> None:
        visible = not getattr(self, attr)
        self.query_one(panel_id).display = visible
        setattr(self, attr, visible)

    def ensure_visible(self, panel_id: str) -> None:
        """拖分隔条时，如果目标面板是收起的，先展开它。"""
        if panel_id == "#sidebar" and not self._sidebar_visible:
            self._toggle("#sidebar", "_sidebar_visible")
        elif panel_id == "#file-panel" and not self._files_visible:
            self._toggle("#file-panel", "_files_visible")

    @on(Button.Pressed, "#btn-sidebar")
    def _on_toggle_sidebar(self) -> None:
        self._toggle("#sidebar", "_sidebar_visible")
        if self._sidebar_visible:
            self._refresh_sessions()

    @on(CollapseBar.Pressed)
    def _on_collapse_bar(self, event: CollapseBar.Pressed) -> None:
        if event.target == "sidebar":
            self._toggle("#sidebar", "_sidebar_visible")
        elif event.target == "file-panel":
            self._toggle("#file-panel", "_files_visible")

    @on(Button.Pressed, "#btn-resume")
    def _on_resume_button(self) -> None:
        self._open_resume()

    @on(Sidebar.SessionSelected)
    def _on_session_selected(self, event: Sidebar.SessionSelected) -> None:
        self._after_resume(event.session_id)

    @on(Button.Pressed, "#btn-files")
    def _on_toggle_files(self) -> None:
        self._toggle("#file-panel", "_files_visible")

    @on(Button.Pressed, "#btn-new")
    async def _on_new(self) -> None:
        await self.action_new_session()

    @on(Button.Pressed, "#btn-clear")
    async def _on_clear(self) -> None:
        await self.action_clear_chat()

    @on(Button.Pressed, "#btn-voice")
    def _on_voice(self) -> None:
        # 第一次点：开始录音；再点：结束录音，随即自动识别
        if self._dots_timer is not None:
            return
        if self._recording:
            self._recording = False
            if self._stop_flag is not None:
                self._stop_flag.set()
            self._voice_log("结束录音，开始识别")
            self._start_thinking()
            return
        self._recording = True
        self._stop_flag = threading.Event()
        self._set_voice_state("recording")
        self._voice_log("开始录音")
        self.run_worker(self._voice_session, thread=True, exclusive=True, group="voice")

    def _voice_log(self, message: str) -> None:
        """语音流程日志，便于排查（写到 <workspace>/.agents/voice.log）。"""
        try:
            path = self.config.workspace / ".agents" / "voice.log"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), message))
        except Exception:  # noqa: BLE001
            pass

    def _set_voice_state(self, state: str) -> None:
        """切换语音按钮状态：idle / recording / thinking。"""
        try:
            button = self.query_one("#btn-voice", Button)
            button.set_class(state == "recording", "recording")
            button.set_class(state == "thinking", "thinking")
            if state == "idle":
                button.label = VOICE_IDLE
            elif state == "recording":
                button.label = VOICE_RECORDING
        except Exception:  # noqa: BLE001
            pass

    def _set_voice_button(self, label: str, recording: bool = False) -> None:
        try:
            button = self.query_one("#btn-voice", Button)
            button.label = label
            if recording:
                button.add_class("recording")
            else:
                button.remove_class("recording")
        except Exception:  # noqa: BLE001
            pass

    def _start_thinking(self) -> None:
        """识别中：话筒后的三个点缓缓起伏，像呼吸。"""
        self._set_voice_state("thinking")
        self._dots_index = 0
        self._tick_thinking()
        if self._dots_timer is None:
            try:
                self._dots_timer = self.set_interval(0.45, self._tick_thinking)
            except Exception:  # noqa: BLE001
                self._dots_timer = None

    def _tick_thinking(self) -> None:
        frames = ("· · ·", "• • •", "● ● ●", "• • •")
        self._dots_index += 1
        try:
            self.query_one("#btn-voice", Button).label = frames[self._dots_index % 4]
        except Exception:  # noqa: BLE001
            pass

    def _stop_thinking(self) -> None:
        if self._dots_timer is not None:
            try:
                self._dots_timer.stop()
            except Exception:  # noqa: BLE001
                pass
            self._dots_timer = None
        self._set_voice_state("idle")

    def _voice_session(self) -> None:
        """录音 -> 本地 Whisper 转写 -> 追加到输入框（不覆盖已有内容）。"""
        started = time.time()
        try:
            text = self._record_and_transcribe()
        except Exception as exc:  # noqa: BLE001
            self._voice_log("识别失败：%r" % exc)
            self.call_from_thread(self.notify, "语音识别失败：%s" % exc, severity="error")
            return
        finally:
            self._recording = False
            self.call_from_thread(self._stop_thinking)
        self._voice_log(
            "识别完成：%.1fs，%d 字" % (time.time() - started, len(text or ""))
        )
        if text:
            self.call_from_thread(self._insert_voice_text, text)

    def _record_and_transcribe(self) -> str:
        """按下后开始录，再次按下 stop 事件置位结束录音，再做本地转写。"""
        import os

        import numpy as np
        import pyaudio

        stop = self._stop_flag
        p = pyaudio.PyAudio()
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=1024,
        )
        frames = []
        try:
            while not stop.is_set():
                frames.append(stream.read(1024, exception_on_overflow=False))
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()
        if not frames:
            return ""
        pcm = b"".join(frames)
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if audio.size == 0:
            return ""

        if self._whisper is None:
            os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
            from faster_whisper import WhisperModel

            self.call_from_thread(self.notify, "首次加载本地语音模型，请稍候…")
            self._whisper = WhisperModel(
                self.config.voice_model,
                device=self.config.voice_device,
                compute_type=self.config.voice_compute_type,
            )
        segments, _info = self._whisper.transcribe(
            audio, language=self.config.voice_language, vad_filter=True, beam_size=1
        )
        text = "".join(seg.text for seg in segments).strip()
        if text:
            # Whisper 中文模型倾向输出繁体，统一转简体
            if self._cc is None:
                from opencc import OpenCC

                self._cc = OpenCC("t2s")
            text = self._cc.convert(text)
        return text

    def _insert_voice_text(self, text: str) -> None:
        """把识别结果插入到输入框光标处，保留已有文字，可继续打字编辑。"""
        prompt_input = self.query_one("#prompt", Input)
        cursor = prompt_input.cursor_position
        prompt_input.value = prompt_input.value[:cursor] + text + prompt_input.value[cursor:]
        prompt_input.cursor_position = cursor + len(text)
        prompt_input.focus()

    # ------------------------------------------------------------------
    # 文件查看
    # ------------------------------------------------------------------
    def _register_file(self, output: str) -> None:
        import re

        match = re.search(r"([A-Za-z]:\\(?:[^（\n]+\\)?[^（\n]+\.\w+)", output)
        if match:
            self.query_one(FilePanel).add_file(match.group(1))

    async def _open_file(self, path: str) -> None:
        from core.tools.fileops import FileSystemService

        content = FileSystemService().read_file(path)
        await self._mount(Markdown("**📄 %s**\n\n```text\n%s\n```" % (path, content)))

    # ------------------------------------------------------------------
    # 事件循环
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # 上下文压缩
    # ------------------------------------------------------------------
    def _start_compact(self) -> None:
        if self._busy:
            self.notify("当前有任务正在执行，无法压缩", severity="warning")
            return
        self._busy = True
        self.query_one("#prompt", Input).disabled = True
        self.notify("开始压缩上下文…")
        self._refresh_status()
        self.run_worker(self._run_compact(), group="turn", exit_on_error=False)

    async def _run_compact(self) -> None:
        try:
            async for event in self.agent.acompact():
                await self._render(event)
        except Exception as exc:  # noqa: BLE001
            await self._mount(ErrorBanner(str(exc)))
        finally:
            self._busy = False
            prompt_input = self.query_one("#prompt", Input)
            prompt_input.disabled = False
            prompt_input.focus()
            self._refresh_status()

    def _start_turn(self, prompt: str) -> None:
        if self._busy:
            self.notify("上一个请求仍在处理中，请稍候", severity="warning")
            return
        self._busy = True
        self.query_one("#prompt", Input).disabled = True
        self._refresh_status()
        self.run_worker(self._run_turn(prompt), group="turn", exit_on_error=False)

    async def _run_turn(self, prompt: str) -> None:
        try:
            async for event in self.agent.arun(prompt):
                await self._render(event)
        except Exception as exc:  # noqa: BLE001 - 保证界面不会因异常退出
            await self._mount(ErrorBanner(str(exc)))
        finally:
            self._busy = False
            self._streaming = None
            self._stream_buffer = ""
            prompt_input = self.query_one("#prompt", Input)
            prompt_input.disabled = False
            prompt_input.focus()
            self._refresh_status()

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------
    async def _render(self, event) -> None:
        if isinstance(event, UserMessageEvent):
            await self._mount(UserBubble(event.text))

        elif isinstance(event, AssistantDeltaEvent):
            if self._streaming is None:
                self._streaming = Markdown("")
                self._stream_buffer = ""
                await self._mount(self._streaming)
            self._stream_buffer += event.text
            now = time.monotonic()
            interval = getattr(self.config, "stream_flush_interval", DEFAULT_STREAM_FLUSH_INTERVAL)
            if now - self._last_flush >= interval:
                self._last_flush = now
                await self._streaming.update(self._stream_buffer)

        elif isinstance(event, AssistantMessageEvent):
            if self._streaming is None:
                self._streaming = Markdown("")
                await self._mount(self._streaming)
            widget = self._streaming
            self._streaming = None
            await widget.update(event.text)

        elif isinstance(event, ToolCallStartedEvent):
            card = ToolCallCard(event.call)
            self._cards[event.call.id] = card
            await self._mount(card)

        elif isinstance(event, ToolCallFinishedEvent):
            card = self._cards.pop(event.call.id, None)
            if card is not None:
                card.set_result(event.execution)
            if event.call.name in ("createFile", "editFile"):
                self._register_file(event.execution.output)

        elif isinstance(event, ErrorEvent):
            await self._mount(ErrorBanner(event.message))

        elif isinstance(event, ContextUsageEvent):
            self._refresh_status()
            if event.warning and not self._warned:
                self._warned = True
                self.notify(
                    "上下文已达窗口 %d%%，请执行 /compact 压缩上下文" % int(event.percent),
                    severity="warning",
                )
            elif not event.warning:
                self._warned = False

        elif isinstance(event, CompactStartedEvent):
            await self._mount(Markdown("**🗜 正在压缩上下文…**"))

        elif isinstance(event, CompactFinishedEvent):
            await self._mount(
                Markdown(
                    "**🗜 上下文压缩完成**（归档编号 `%s`）\n\n%s"
                    % (event.archive_id, event.summary)
                )
            )
            self.push_screen(CompactLogScreen(event.before, event.after))
            self.notify("上下文压缩完成，归档编号 %s" % event.archive_id)

        elif isinstance(event, CompactFailedEvent):
            await self._mount(ErrorBanner("压缩失败：%s" % event.message))

        elif isinstance(event, TurnCompletedEvent):
            self._refresh_status()

    async def _mount(self, widget) -> None:
        chat_log = self.query_one("#chat-log", VerticalScroll)
        await chat_log.mount(widget)
        chat_log.scroll_end(animate=False)

    async def _show_welcome(self) -> None:
        text = (
            "**玄机真人**\n"
            "模型：%s\n"
            "已备：八字 · 紫微 · 塔罗 · 占星 · 六爻 · 梅花易数 · 奇门 · 风水 · 数字命理\n\n"
            "直接输入问题即可，例如「帮我看看八字姻缘」「塔罗测今日运势」。"
            % (
                self.config.llm.model,
            )
        )
        await self._mount(Markdown(text))

    def _refresh_status(self) -> None:
        status = self.query_one("#status-bar", StatusBar)
        state = "处理中…" if self._busy else "就绪"
        ctx = self.agent.context_status()
        used_k = ctx["used"] / 1000.0
        window_k = ctx["window"] / 1000.0
        default_mark = "（默认）" if ctx.get("window_is_default") else ""
        context_line = "上下文 %.1fk / %.0fk%s ｜ %.1f%%" % (
            used_k,
            window_k,
            default_mark,
            ctx["percent"],
        )
        mcp = self._mcp_status or {}
        servers = mcp.get("servers") or {}
        if not mcp.get("available"):
            mcp_line = "MCP 未接入"
        else:
            mcp_line = "MCP %d/%d · 工具 %d" % (
                sum(1 for s in servers.values() if s.get("connected")),
                len(servers),
                mcp.get("tool_count", 0),
            )
        status.update(
            "%s ｜ 模型 %s ｜ 工具 %d 个 ｜ %s ｜ 状态 %s"
            % (
                context_line,
                self.config.llm.model,
                len(self.agent.registry.names),
                mcp_line,
                state,
            )
        )


def run_tui(agent: Optional[Agent] = None, config: Optional[AppConfig] = None,
            config_path: Optional[str] = None) -> None:
    """启动终端界面。"""
    config = config or load_config(config_path)
    agent = agent or build_agent(config)
    XAgentApp(agent=agent, config=config).run()
