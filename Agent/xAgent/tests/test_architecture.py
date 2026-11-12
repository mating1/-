# -*- coding: utf-8 -*-
"""架构约束测试：保证"核心与界面分离"不会在后续开发中被破坏。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Set

ROOT = Path(__file__).resolve().parent.parent
CORE_DIR = ROOT / "core"
TUI_DIR = ROOT / "tui"

FORBIDDEN_IN_CORE = {"textual", "rich", "fastapi", "flask", "django", "tkinter", "PyQt5", "PySide6"}
FORBIDDEN_IN_TUI = {"requests", "urllib3"}


def _imported_modules(package_dir: Path) -> Set[str]:
    modules: Set[str] = set()
    for path in package_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    continue  # 包内相对导入
                if node.module:
                    modules.add(node.module.split(".")[0])
    return modules


def test_core_has_no_frontend_dependency():
    offenders = _imported_modules(CORE_DIR) & FORBIDDEN_IN_CORE
    assert not offenders, "core 层不允许依赖前端框架：%s" % ", ".join(sorted(offenders))


def test_tui_does_not_call_http_directly():
    offenders = _imported_modules(TUI_DIR) & FORBIDDEN_IN_TUI
    assert not offenders, "tui 层不允许直接访问网络：%s" % ", ".join(sorted(offenders))


def test_core_and_tui_are_separate_top_level_packages():
    assert CORE_DIR.is_dir() and (CORE_DIR / "__init__.py").exists()
    assert TUI_DIR.is_dir() and (TUI_DIR / "__init__.py").exists()
    assert not (CORE_DIR / "tui").exists()
    assert not (TUI_DIR / "core").exists()


def test_public_core_api_is_importable():
    sys.path.insert(0, str(ROOT))
    import core

    for name in ("Agent", "AppConfig", "load_config", "build_agent", "ToolRegistry"):
        assert hasattr(core, name), "core 未导出 %s" % name
