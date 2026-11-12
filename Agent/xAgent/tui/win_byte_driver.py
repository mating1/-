# -*- coding: utf-8 -*-
"""Windows 混合输入驱动。

背景：Textual 自带的 WindowsDriver 用 ``ReadConsoleInputW`` 读 Win32
``INPUT_RECORD``。在 ConPTY / Windows Terminal 下：

- 键盘按键以 ``KEY_EVENT_RECORD`` 进入控制台输入缓冲（走 ReadConsoleInputW，
  旧驱动这条路一直是通的）；
- 鼠标点击/移动/滚轮不投 ``MOUSE_EVENT_RECORD``（microsoft/terminal #376
  的 Win32 鼠标通道长期未实现），而是以 VT SGR 字节经 stdin 管道返回，
  ReadConsoleInputW 收不到，导致整窗鼠标失灵。

因此本驱动保留父类的 ``EventMonitor`` 线程处理键盘与窗口尺寸事件，另起一个
``os.read`` 字节流线程读取 stdin 管道里的鼠标 SGR 序列，交给 XTermParser 解析。
两条通道在 ConPTY 下读取不同队列，互不抢占。
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import sys
import time
from codecs import getincrementaldecoder
from threading import Thread
from typing import Optional

from textual._xterm_parser import XTermParser
from textual.drivers import win32
from textual.drivers._writer_thread import WriterThread
from textual.drivers.windows_driver import WindowsDriver
from textual.events import Resize
from textual.geometry import Size


class WindowsByteDriver(WindowsDriver):
    """Windows 下 EventMonitor(键盘/尺寸) + os.read(鼠标 SGR) 的混合驱动。"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._key_thread: Optional[Thread] = None
        self._size_thread: Optional[Thread] = None

    def _enable_mouse_support(self) -> None:
        """只保留探针实测可用的鼠标序列（去掉 1015h URXVT highlight）。"""
        if not self._mouse:
            return
        write = self.write
        write("\x1b[?1000h")  # SET_VT200_MOUSE
        write("\x1b[?1003h")  # SET_ANY_EVENT_MOUSE
        write("\x1b[?1006h")  # SET_SGR_EXT_MODE_MOUSE
        self.flush()

    def start_application_mode(self) -> None:
        """启动应用模式：EventMonitor 管键盘/尺寸，os.read 线程管鼠标字节流。"""
        loop = asyncio.get_running_loop()

        self._restore_console = win32.enable_application_mode()

        self._writer_thread = WriterThread(self._file)
        self._writer_thread.start()

        self.write("\x1b[?1049h")  # Alt screen
        self._enable_mouse_support()
        self.write("\x1b[?25l")  # Hide cursor
        self.write("\033[?1004h")  # FocusIn/FocusOut
        # 不开启 Kitty 键盘协议（>1u）：WT 对该协议支持不完整。
        self.flush()
        self._enable_bracketed_paste()

        # 键盘 + 窗口尺寸：走父类 EventMonitor（ReadConsoleInputW / KEY_EVENT）。
        self._event_thread = win32.EventMonitor(
            loop, self._app, self.exit_event, self.process_message
        )
        self._event_thread.start()

        # 鼠标 SGR 字节：走 stdin 管道 os.read。
        self._key_thread = Thread(
            target=self._run_input_thread, name="textual-mouse", daemon=True
        )
        self._key_thread.start()

        # 尺寸轮询：ConPTY 下 WINDOW_BUFFER_SIZE_EVENT 时有时无，最大化后界面
        # 仍按旧高度布局导致下半黑；这里周期读控制台窗口尺寸，变化就补发 Resize。
        self._size_thread = Thread(
            target=self._run_size_poller, name="textual-size", daemon=True
        )
        self._size_thread.start()

    def disable_input(self) -> None:
        """停止两条输入线程。"""
        try:
            self._disable_mouse_support()
            self.exit_event.set()
            if self._event_thread is not None:
                self._event_thread.join()
                self._event_thread = None
            if self._key_thread is not None:
                # 阻塞在 os.read 上的线程无法被立即打断，daemon 线程随进程退出；
                # join 只等有限时间，避免退出流程卡死。
                self._key_thread.join(timeout=1.0)
                self._key_thread = None
            if self._size_thread is not None:
                self._size_thread.join(timeout=1.0)
                self._size_thread = None
            self.exit_event.clear()
        except Exception:
            pass

    def stop_application_mode(self) -> None:
        self._disable_bracketed_paste()
        self.disable_input()

        self.write("\x1b[<u")
        self.write("\x1b[?1049l" + "\x1b[?25h")
        self.write("\033[?1004l")
        self.flush()

    def close(self) -> None:
        if self._writer_thread is not None:
            self._writer_thread.stop()
        if self._restore_console:
            self._restore_console()

    def _run_input_thread(self) -> None:
        """从 stdin 管道读取鼠标 SGR 字节，交给 XTermParser 解析。

        Windows 上 ``select()`` / SelectSelector 只支持 socket，不能注册控制台/
        管道句柄，这里直接阻塞 ``os.read``（探针已验证 ConPTY stdin 可被 os.read
        读到鼠标 SGR）。键盘按键走 EventMonitor 通道，不在这里处理。
        """
        fileno = sys.__stdin__.fileno()
        parser = XTermParser(self._debug)
        decode = getincrementaldecoder("utf-8")().decode
        read = os.read

        try:
            while not self.exit_event.is_set():
                data = read(fileno, 1024 * 4)
                if not data:
                    break
                for event in parser.feed(decode(data)):
                    self.process_message(event)
                for event in parser.tick():
                    self.process_message(event)
        except Exception as error:
            self._app.log.error("BYTE INPUT THREAD ERROR", error)

    def _run_size_poller(self) -> None:
        """周期读取控制台窗口尺寸，变化时补发 Resize（ConPTY 尺寸事件不可靠）。"""
        from ctypes import wintypes

        class COORD(ctypes.Structure):
            _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

        class SMALL_RECT(ctypes.Structure):
            _fields_ = [
                ("Left", wintypes.SHORT), ("Top", wintypes.SHORT),
                ("Right", wintypes.SHORT), ("Bottom", wintypes.SHORT),
            ]

        class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
            _fields_ = [
                ("dwSize", COORD),
                ("dwCursorPosition", COORD),
                ("srWindow", SMALL_RECT),
                ("wAttributes", wintypes.WORD),
                ("dwMaximumWindowSize", COORD),
            ]

        import shutil

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle_out = k32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        csbi = CONSOLE_SCREEN_BUFFER_INFO()
        last: Optional[tuple[int, int]] = None

        while not self.exit_event.is_set():
            try:
                ok = k32.GetConsoleScreenBufferInfo(handle_out, ctypes.byref(csbi))
                # ConPTY 下 srWindow 字段不可靠（Left/Right 会出现反序负值），
                # 缓冲尺寸 dwSize 与 shutil.get_terminal_size() 才跟随真实窗口大小。
                ts = shutil.get_terminal_size()
                width = csbi.dwSize.X if ok and csbi.dwSize.X > 0 else ts.columns
                height = csbi.dwSize.Y if ok and csbi.dwSize.Y > 0 else ts.lines
                if width > 0 and height > 0 and (width, height) != last:
                    last = (width, height)
                    self._size = (width, height)
                    self.send_message(Resize(Size(width, height), Size(width, height)))
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.5)
