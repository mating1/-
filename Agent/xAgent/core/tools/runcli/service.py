# -*- coding: utf-8 -*-
"""本地 CLI 命令执行服务（带命令安全拦截）。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Set

MAX_OUTPUT = 20000

# 破坏性 / 提权 / 解释器逃逸 / 下载执行类命令，默认一律拦截。
BLOCKED_COMMANDS: Set[str] = {
    # 删除与格式化
    "rm", "del", "erase", "rmdir", "rd", "format", "mkfs", "mkfs.ext4",
    "fdisk", "diskpart", "dd",
    # 关机 / 重启 / 运行级
    "shutdown", "reboot", "halt", "poweroff", "init", "runlevel",
    # 注册表 / 系统配置
    "reg", "regedit", "regsvr32",
    # 可借 shell 拼接逃逸的解释器（shell=False 下仍可能被用来开子进程）
    "bash", "sh", "zsh", "fish", "cmd", "cmd.exe", "powershell",
    "pwsh", "pwsh.exe", "wscript", "cscript", "wsl",
    # 下载落地执行
    "curl", "wget", "bitsadmin", "certutil",
    # 权限改写
    "chmod", "chown", "chgrp",
}

# 参数中出现即视为 shell 拼接 / 重定向意图，拦截。
DANGEROUS_ARG_SEPARATORS = ("|", ">", ">>", "&&", ";", "`", "$(")


class RunCliService:
    def __init__(
        self,
        timeout: int = 30,
        max_output: int = MAX_OUTPUT,
        allowed_commands: Optional[List[str]] = None,
    ) -> None:
        self.timeout = timeout
        self.max_output = max_output
        self.allowed_commands = {c.lower() for c in allowed_commands} if allowed_commands else None

    def _guard(self, command: str, args: List[str]) -> Optional[str]:
        """返回拦截原因；放行返回 None。"""
        if not command:
            return "command 不能为空"
        name = Path(command).name.lower()
        if self.allowed_commands is not None and name not in self.allowed_commands:
            return "命令不在允许清单内：%s" % command
        if name in BLOCKED_COMMANDS:
            return "命令被安全策略拦截（破坏性/解释器/下载执行类）：%s" % command
        joined = " ".join(args or [])
        for sep in DANGEROUS_ARG_SEPARATORS:
            if sep in joined:
                return "参数中包含 shell 拼接/重定向符号，已拦截：%s" % sep
        return None

    def run_cli(self, command: str, args: Optional[List[str]] = None) -> str:
        guard = self._guard(command, args or [])
        if guard is not None:
            return "已拒绝执行：%s" % guard
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
