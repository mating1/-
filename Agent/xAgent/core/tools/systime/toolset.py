# -*- coding: utf-8 -*-
"""系统时间工具集。"""

from __future__ import annotations

from typing import List

from ..base import FunctionTool, Tool
from .service import SystemTimeService

TOOL_GET_DATE = "getDate"
TOOL_IS_LEAP_YEAR = "isLeapYear"


def build_systime_tools(service: SystemTimeService = None) -> List[Tool]:
    service = service or SystemTimeService()
    return [
        FunctionTool(
            name=TOOL_GET_DATE,
            description="获取当前电脑的日期和时间，通过调用本地 date/time 命令实现",
            parameters={"type": "object", "properties": {}, "required": []},
            func=lambda **_: service.get_date(),
        ),
        FunctionTool(
            name=TOOL_IS_LEAP_YEAR,
            description="判断输入的年份是否是闰年",
            parameters={
                "type": "object",
                "properties": {
                    "year": {"type": "integer", "description": "要判断的年份，例如 2024"},
                },
                "required": ["year"],
            },
            func=lambda year: service.is_leap_year(year),
        ),
    ]
