# -*- coding: utf-8 -*-
"""RunCli 安全拦截单测。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.tools.runcli.service import RunCliService  # noqa: E402


def test_blocked_destructive_command():
    svc = RunCliService()
    out = svc.run_cli("rm", ["-rf", "/"])
    assert "拦截" in out and "rm" in out


def test_blocked_shell_interpreter():
    svc = RunCliService()
    out = svc.run_cli("powershell", ["-c", "whoami"])
    assert "拦截" in out
    out = svc.run_cli("cmd", ["/c", "dir"])
    assert "拦截" in out


def test_blocked_download_exec():
    svc = RunCliService()
    out = svc.run_cli("curl", ["http://x/y"])
    assert "拦截" in out


def test_blocked_shell_metacharacters_in_args():
    svc = RunCliService()
    out = svc.run_cli("python", ["a.py", ";", "rm -rf /"])
    assert "拼接" in out or "拦截" in out


def test_empty_command():
    svc = RunCliService()
    out = svc.run_cli("")
    assert "不能为空" in out


def test_unknown_allowed_command_reports_not_found_not_blocked():
    svc = RunCliService()
    out = svc.run_cli("definitely-not-installed-cmd-xyz", ["--version"])
    assert "未找到" in out
    assert "拦截" not in out


def test_whitelist_restricts_commands():
    svc = RunCliService(allowed_commands=["dir"])
    out = svc.run_cli("git", ["status"])
    assert "允许清单" in out
