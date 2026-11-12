# -*- coding: utf-8 -*-
"""xAgent 统一入口。

    python main.py            # 启动 TUI
    python main.py --config xxx.ini
"""

from __future__ import annotations

import argparse
import sys


def _fix_console_encoding() -> None:
    """Windows 控制台默认可能是 GBK，这里统一成 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main() -> int:
    parser = argparse.ArgumentParser(prog="xagent", description="xAgent 玄学命理顾问 Agent（核心与界面分离）")
    parser.add_argument("--config", help="config.ini 路径")
    parser.add_argument(
        "--web",
        action="store_true",
        help="预留：启动 Web 前端（尚未实现）",
    )
    args = parser.parse_args()

    _fix_console_encoding()

    if args.web:
        print("Web 前端尚未实现，请使用 `python main.py` 启动 TUI。", file=sys.stderr)
        return 1

    from tui.app import run_tui

    try:
        run_tui(config_path=args.config)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        print("启动失败：%s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
