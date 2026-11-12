# -*- coding: utf-8 -*-
"""文件操作扩展语义与路径边界单测。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.errors import ToolError  # noqa: E402
from core.tools.fileops import FileSystemService  # noqa: E402


def test_create_and_delete_dir(tmp_path):
    service = FileSystemService(root=str(tmp_path))

    created = service.create_dir("a/b/c")
    assert "已创建目录" in created
    assert (tmp_path / "a" / "b" / "c").is_dir()

    # 非空目录默认拒绝删除
    (tmp_path / "a" / "b" / "c" / "x.txt").write_text("x", encoding="utf-8")
    try:
        service.delete_dir("a/b")
    except ToolError as exc:
        assert "非空" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("非空目录应被拒绝删除")

    removed = service.delete_dir("a", recursive=True)
    assert "已删除目录" in removed
    assert not (tmp_path / "a").exists()


def test_delete_file(tmp_path):
    f = tmp_path / "g.txt"
    f.write_text("g", encoding="utf-8")
    service = FileSystemService(root=str(tmp_path))
    assert "已删除文件" in service.delete_file("g.txt")
    assert not f.exists()

    # 目录不能走 delete_file
    d = tmp_path / "d"
    d.mkdir()
    try:
        service.delete_file("d")
    except ToolError as exc:
        assert "目录" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("目录删除应走删除目录工具")


def test_rename_move_file_and_dir(tmp_path):
    service = FileSystemService(root=str(tmp_path))
    (tmp_path / "old.txt").write_text("hi", encoding="utf-8")

    moved = service.rename_move("old.txt", "sub/new.txt")
    assert "new.txt" in moved
    assert (tmp_path / "sub" / "new.txt").read_text(encoding="utf-8") == "hi"

    # 目标已存在时拒绝覆盖
    (tmp_path / "sub" / "dup.txt").write_text("a", encoding="utf-8")
    try:
        service.rename_move("sub/new.txt", "sub/dup.txt")
    except ToolError as exc:
        assert "未覆盖" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("覆盖目标应被拒绝")


def test_get_file_type_distinguishes_dir_and_file(tmp_path):
    (tmp_path / "note.txt").write_text("hi", encoding="utf-8")
    (tmp_path / "folder").mkdir()
    service = FileSystemService(root=str(tmp_path))

    assert "类型：目录" in service.get_file_type("folder")
    assert "类型：文件" in service.get_file_type("note.txt")


def test_path_boundary_blocks_escape(tmp_path):
    service = FileSystemService(root=str(tmp_path))
    outside = tmp_path.parent / "should_not_touch.txt"
    try:
        service.read_file("../should_not_touch.txt")
    except ToolError as exc:
        assert "工作目录之外" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("越界路径应被拒绝")
    assert not outside.exists()


def test_no_root_keeps_legacy_behavior(tmp_path):
    service = FileSystemService()
    service.create_file(str(tmp_path), "legacy.txt", "ok")
    assert (tmp_path / "legacy.txt").read_text(encoding="utf-8") == "ok"


def test_strict_root_without_root_rejects_access(tmp_path):
    service = FileSystemService(strict_root=True)
    try:
        service.read_file(str(tmp_path / "note.txt"))
    except ToolError as exc:
        assert "未配置工作目录" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("strict_root 下无 root 应拒绝访问")
