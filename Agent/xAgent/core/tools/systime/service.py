# -*- coding: utf-8 -*-
"""系统时间与简单计算服务。"""

from __future__ import annotations

from datetime import datetime

_WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


class SystemTimeService:
    """基于标准库获取本地日期时间，以及闰年判断，跨平台可用。"""

    def get_date(self) -> str:
        now = datetime.now().astimezone()
        weekday = _WEEKDAYS[now.weekday()]
        return "%s %s（本地时区 %s）" % (
            now.strftime("%Y-%m-%d %H:%M:%S"),
            weekday,
            now.strftime("%z"),
        )

    def is_leap_year(self, year: int) -> str:
        y = int(year)
        leap = (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)
        return "%d 年%s闰年" % (y, "是" if leap else "不是")
