# -*- coding: utf-8 -*-
"""系统时间与简单计算服务。"""

from __future__ import annotations

import subprocess
import sys


class SystemTimeService:
    """调用本地 date/time 命令获取时间，以及闰年判断。"""

    def get_date(self) -> str:
        result = subprocess.run(
            "date /t & time /t",
            shell=True,
            capture_output=True,
        )
        text = self._decode(result.stdout).strip()
        if result.returncode != 0:
            err = self._decode(result.stderr).strip()
            return "调用本地命令失败（exit=%s）：%s" % (result.returncode, err or text)
        return text.replace("\r\n", "\n").replace("\r", "\n")

    def is_leap_year(self, year: int) -> str:
        y = int(year)
        leap = (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)
        return "%d 年%s闰年" % (y, "" if leap else "不是")

    @staticmethod
    def _decode(raw: bytes) -> str:
        for enc in ("utf-8", "gbk", sys.getfilesystemencoding()):
            try:
                return raw.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return raw.decode("utf-8", errors="replace")
