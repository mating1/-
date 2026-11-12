# -*- coding: utf-8 -*-
"""时间工具单测：跨平台取时与闰年规则。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.tools.systime import SystemTimeService  # noqa: E402


def test_get_date_returns_local_timestamp():
    text = SystemTimeService().get_date()
    assert "20" in text
    assert "-" in text
    assert "本地时区" in text


def test_leap_year_rule():
    svc = SystemTimeService()
    assert "是闰年" in svc.is_leap_year(2024)
    assert "不是闰年" in svc.is_leap_year(2023)
    # 整百年须被 400 整除
    assert "是闰年" in svc.is_leap_year(2000)
    assert "不是闰年" in svc.is_leap_year(1900)
