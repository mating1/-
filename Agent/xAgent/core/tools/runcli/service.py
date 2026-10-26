# -*- coding: utf-8 -*-
"""本地 CLI 命令执行服务。"""

from __future__ import annotations

import subprocess
import sys
from typing import List, Optional

MAX_OUTPUT = 20000


class RunCliService:
    def __init__(self, timeout: int = 30, max_output: int = MAX_OUTPUT) -> None:
        self.timeout = timeout
        self.max_output = max_output

    def run_cli(self, command: str, args: Optional[List[str]] = None) -> str:
        if not command:
            return "command 不能为空"
        argv = [command] + list(args or [])
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                timeout=self.timeout,
                shell=False,
            )
        except FileNotFoundError:
            return "命令未找到：%s" % command
        except subprocess.TimeoutExpired:
            return "命令执行超时（>%ss）：%s" % (self.timeout, command)
        except OSError as exc:
            return "调用命令失败：%s" % exc

        out = self._decode(proc.stdout)
        err = self._decode(proc.stderr)
        out_truncated = self._truncate(out, "stdout")
        err_truncated = self._truncate(err, "stderr")

        parts = ["exit code: %d" % proc.returncode]
        parts.append("--- stdout ---")
        parts.append(out_truncated)
        if err.strip():
            parts.append("--- stderr ---")
            parts.append(err_truncated)
        return "\n".join(parts)

    def _truncate(self, text: str, label: str) -> str:
        if len(text) <= self.max_output:
            return text
        return text[: self.max_output] + "\n...[截断，%s 共 %d 字符，仅保留前 %d 字符]" % (
            label, len(text), self.max_output
        )

    @staticmethod
    def _decode(raw: bytes) -> str:
        for enc in ("utf-8", "gbk", sys.getfilesystemencoding()):
            try:
                return raw.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return raw.decode("utf-8", errors="replace")
