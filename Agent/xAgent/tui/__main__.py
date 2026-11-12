# -*- coding: utf-8 -*-
"""``python -m tui`` 启动终端界面。"""

from __future__ import annotations

import sys

from .app import run_tui


def main() -> int:
    try:
        run_tui()
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        print("启动失败：%s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
