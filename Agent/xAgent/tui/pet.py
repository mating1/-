# -*- coding: utf-8 -*-
"""xAgent 的吉祥物：一只横放的长方形小黑脸，会眨眼、会笑、会 wink。

渲染方式：像素网格 -> 半块字符（▀），上半个是前景色、下半个是背景色，
所以在终端里也能看到一块真正的小彩色脸。整块浮在界面最上层，
可以用鼠标拖着走，点一下会有表情反应。
"""

from __future__ import annotations

import math
import random
import time
from datetime import datetime

from rich.style import Style
from rich.text import Text
from textual.widgets import Static

# 像素网格：宽 = 字符列数，高 = 2 × 行数
GRID_W = 18
GRID_H = 10

FACE = "#1B1B22"
EYE = "#5FD8FF"
EYE_LIGHT = "#F0FFFF"
BLUSH = "#FF9C89"
MOUTH = "#5FD8FF"
BACKDROP = "#FBF7FD"

OPEN, BLINK, SMILE, WINK = "open", "blink", "smile", "wink"

# 五官基准（像素坐标，整数更可控）
EYE_Y = 3
EYE_LX, EYE_RX = 4, 11
BLUSH_Y = 6
BLUSH_LX, BLUSH_RX = 1, 15
MOUTH_X, MOUTH_Y = 9, 7


def _blank() -> list:
    # None 表示透明：渲染时这一格不画背景，露出下面的界面
    return [[None for _ in range(GRID_W)] for _ in range(GRID_H)]


def _rounded_rect(px: list, x0: int, y0: int, x1: int, y1: int, r: float,
                  color: str) -> None:
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            dx = 0
            dy = 0
            if x < x0 + r:
                dx = x0 + r - x
            elif x > x1 - r:
                dx = x - (x1 - r)
            if y < y0 + r:
                dy = y0 + r - y
            elif y > y1 - r:
                dy = y - (y1 - r)
            if dx * dx + dy * dy <= r * r + 0.4:
                px[y][x] = color


def _ellipse(px: list, cx: float, cy: float, rx: float, ry: float, color: str) -> None:
    for y in range(int(cy - ry) - 1, int(cy + ry) + 2):
        for x in range(int(cx - rx) - 1, int(cx + rx) + 2):
            if not (0 <= x < GRID_W and 0 <= y < GRID_H):
                continue
            if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0:
                px[y][x] = color


def _arc_up(px: list, cx: float, cy: float, rx: float, ry: float, color: str) -> None:
    """∩ 形的笑眼：只取椭圆的上半圈，1 像素粗。"""
    for x in range(int(cx - rx), int(cx + rx) + 1):
        ratio = (x - cx) / rx
        if abs(ratio) > 1:
            continue
        y = int(round(cy - ry * math.sqrt(max(0.0, 1 - ratio * ratio))))
        if 0 <= y < GRID_H and 0 <= x < GRID_W:
            px[y][x] = color


def _base() -> list:
    # 整块网格填满黑脸：不留透明边，拖到哪里都不会露出底下的色块
    px = [[FACE for _ in range(GRID_W)] for _ in range(GRID_H)]
    return px


def _blush(px: list) -> None:
    for x0 in (BLUSH_LX, BLUSH_RX):
        for x in (x0, x0 + 1):
            if 0 <= x < GRID_W:
                px[BLUSH_Y][x] = BLUSH


def _omega(px: list) -> None:
    """小猫嘴：横向三个格子并排。"""
    cy = MOUTH_Y
    for dx in (-1, 0, 1):
        x = MOUTH_X + dx
        if 0 <= x < GRID_W and cy < GRID_H:
            px[cy][x] = MOUTH


def _eyes_open(px: list, left: bool = True, right: bool = True) -> None:
    for bx, on in ((EYE_LX, left), (EYE_RX, right)):
        if not on:
            continue
        for y in (2, 3, 4, 5):
            for x in range(bx, bx + 4):
                px[y][x] = EYE


def _eyes_blink(px: list) -> None:
    for bx in (EYE_LX, EYE_RX):
        for x in range(bx, bx + 4):
            px[3][x] = EYE


def _eyes_smile(px: list, left: bool = True, right: bool = True) -> None:
    for bx, on in ((EYE_LX, left), (EYE_RX, right)):
        if not on:
            continue
        px[4][bx + 1] = EYE
        px[4][bx + 2] = EYE
        px[3][bx] = EYE
        px[3][bx + 3] = EYE


def pixels(state: str) -> list:
    """返回某一状态下的像素网格（预览与调试用）。"""
    px = _base()
    _blush(px)
    if state == BLINK:
        _eyes_blink(px)
    elif state == SMILE:
        _eyes_smile(px)
    elif state == WINK:
        # 一只眼睁着，一只眼眯成弯月
        _eyes_open(px, left=True, right=False)
        _eyes_smile(px, left=False, right=True)
        _omega(px)
        return px
    else:
        _eyes_open(px)
    _omega(px)
    return px


def _frame(state: str) -> Text:
    px = pixels(state)
    text = Text(no_wrap=True)
    for y in range(0, GRID_H, 2):
        top = px[y]
        bottom = px[y + 1]
        for i in range(GRID_W):
            up, down = top[i], bottom[i]
            if up is None and down is None:
                text.append(" ")
            elif down is None:
                text.append("▀", style=Style(color=up))
            elif up is None:
                text.append("▄", style=Style(color=down, bgcolor=None))
            else:
                text.append("▀", style=Style(color=up, bgcolor=down))
        if y + 2 < GRID_H:
            text.append("\n")
    return text


_FRAMES = {state: _frame(state) for state in (OPEN, BLINK, SMILE, WINK)}


def _read_offset(side) -> int:
    """把 Textual 的 offset 分量（Scalar 或元组）读成整数格数。"""
    value = getattr(side, "value", side)
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


# 点一下它时冒出来的关心话
# 带时段的话只在该时段出现；ALWAYS 里的是随时都合适的
GREETINGS = {
    "early": ["早上好呀～", "新的一天开始啦", "记得吃早饭哦"],
    "forenoon": ["上午好～", "忙到现在了，喝口水吧", "坐久了站起来动一动～"],
    "noon": ["中午好呀～", "吃午饭了吗？", "中午眯一会儿吧"],
    "afternoon": ["下午好～", "喝口水歇一歇吧", "困了就伸个懒腰～"],
    "evening": ["晚上好呀～", "晚饭吃了吗？", "今天累不累？"],
    "night": ["这么晚还没睡呀？", "早点休息哦～", "别熬夜啦，明天还有精神点"],
}

ALWAYS = [
    "想我了吗？",
    "我一直在这儿陪着你",
    "别皱眉，摸摸头～",
    "慢慢来，不着急",
    "今天已经很棒了",
]


def pick_phrase() -> str:
    """按时段挑一句话，一半概率说当下这个时间的问候。"""
    hour = datetime.now().hour
    if 5 <= hour < 9:
        slot = "early"
    elif 9 <= hour < 11:
        slot = "forenoon"
    elif 11 <= hour < 14:
        slot = "noon"
    elif 14 <= hour < 17:
        slot = "afternoon"
    elif 17 <= hour < 19:
        slot = "evening"
    elif 19 <= hour < 23:
        slot = "evening"
    else:
        slot = "night"

    pool = GREETINGS[slot]
    if random.random() < 0.55:
        return random.choice(pool)
    return random.choice(ALWAYS)


def _text_cols(text: str) -> int:
    """粗略算一行中文的栏宽：汉字占两列，ASCII 占一列。"""
    return sum(1 if ord(ch) < 128 else 2 for ch in text)


class SpeechBubble(Static):
    """跟在脸旁边的对话气泡，点一下脸就冒出来，过一会儿自己消失。"""

    can_focus = False

    def __init__(self) -> None:
        super().__init__("", id="pet-bubble", markup=False)
        self.display = False
        self._hide_timer = None

    def show_bubble(self) -> None:
        self.display = True
        if self._hide_timer is not None:
            try:
                self._hide_timer.stop()
            except Exception:  # noqa: BLE001
                pass
        self._hide_timer = self.set_timer(2.8, self._hide)

    def _hide(self) -> None:
        self.display = False
        self._hide_timer = None


class Pet(Static):
    """浮在界面上的小吉祥物：可拖动、可点击。"""

    can_focus = False

    def __init__(self) -> None:
        super().__init__(_FRAMES[OPEN], id="pet", markup=False)
        self._drag = False
        self._moved = False
        self._press_x = 0
        self._press_y = 0
        self._start_offset = (0, 0)
        self._action: str | None = None
        self._action_until = 0.0
        self._click_count = 0
        self._blink_left = 0
        self._blink_on = False
        self._blink_next = 0.0
        self._next_blink = time.monotonic() + 5.0
        self._timer = None

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.12, self._tick)

    # -- 动画 ----------------------------------------------------------
    def _paint(self, state: str) -> None:
        try:
            self.update(_FRAMES[state])
        except Exception:  # noqa: BLE001 - 界面关闭时忽略
            pass

    def _tick(self) -> None:
        now = time.monotonic()
        if self._action is not None:
            if now >= self._action_until:
                self._action = None
                self._paint(OPEN)
            return
        if self._blink_on:
            if now >= self._blink_next:
                self._blink_on = False
                self._paint(OPEN)
            return
        if now >= self._next_blink:
            self._blink_on = True
            self._blink_next = now + 0.18
            self._next_blink = now + 5.0
            self._paint(BLINK)

    def _trigger(self) -> None:
        self._click_count += 1
        self._action = SMILE if self._click_count % 2 else WINK
        self._action_until = time.monotonic() + (1.2 if self._action == SMILE else 1.5)
        self._paint(self._action)
        self._say()

    def _say(self) -> None:
        """在脸右边冒一句话；右边放不下就改放左边。"""
        try:
            bubble = self.app.query_one("#pet-bubble", SpeechBubble)
        except Exception:  # noqa: BLE001
            return
        text = pick_phrase()
        bubble.update(text)
        bx = _read_offset(self.styles.offset.x)
        by = _read_offset(self.styles.offset.y)
        width = _text_cols(text) + 4  # 左右各一格留白 + 边框
        screen_w = self.app.size.width
        x = bx + GRID_W + 1
        if x + width > screen_w:
            x = max(0, bx - width - 1)
        bubble.styles.offset = (x, by + 1)
        bubble.show_bubble()

    # -- 鼠标：拖动 + 点击 ---------------------------------------------
    def on_mouse_down(self, event) -> None:
        self._drag = True
        self._moved = False
        try:
            self.app.query_one("#pet-bubble", SpeechBubble).display = False
        except Exception:  # noqa: BLE001
            pass
        self._press_x = getattr(event, "screen_x", event.x)
        self._press_y = getattr(event, "screen_y", event.y)
        off = self.styles.offset
        self._start_offset = (_read_offset(off.x), _read_offset(off.y))
        try:
            self.capture_mouse()
        except Exception:  # noqa: BLE001
            pass
        event.stop()

    def on_mouse_move(self, event) -> None:
        if not self._drag:
            return
        x = getattr(event, "screen_x", event.x)
        y = getattr(event, "screen_y", event.y)
        dx = x - self._press_x
        dy = y - self._press_y
        if abs(dx) > 1 or abs(dy) > 1:
            self._moved = True
        self.styles.offset = (max(-2, self._start_offset[0] + dx),
                              max(-1, self._start_offset[1] + dy))
        event.stop()

    def on_mouse_up(self, event) -> None:
        if self._drag:
            self._drag = False
            try:
                self.release_mouse()
            except Exception:  # noqa: BLE001
                pass
            if not self._moved:
                self._trigger()
        event.stop()
