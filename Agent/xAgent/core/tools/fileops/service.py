# -*- coding: utf-8 -*-
"""文件系统业务服务。

这一层只做"文件操作"这件事：错误通过 ToolError 抛出，
不关心调用者是谁（模型 / 测试 / 未来的其他前端）。
"""

from __future__ import annotations

import mimetypes
import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from ...errors import ToolError

DEFAULT_MAX_READ_CHARS = 50000


class FileSystemService:
    """基于本地磁盘的文件系统服务。"""

    def __init__(self, max_read_chars: int = DEFAULT_MAX_READ_CHARS) -> None:
        self.max_read_chars = max_read_chars

    # ------------------------------------------------------------------
    # 目录
    # ------------------------------------------------------------------
    def get_cwd(self) -> str:
        """获取当前工作目录。"""
        return str(Path.cwd())

    def list_dir(self, path: str = ".") -> str:
        """列出目录下的所有文件和子目录。"""
        target = Path(path or ".")
        if not target.is_dir():
            raise ToolError("目录不存在：%s" % path)

        entries: List[Tuple[bool, str]] = []
        with os.scandir(str(target)) as iterator:
            for entry in iterator:
                entries.append((entry.is_dir(), entry.name))
        entries.sort(key=lambda item: (not item[0], item[1].lower()))

        header = "目录 %s，共 %d 项" % (target.resolve(), len(entries))
        if not entries:
            return header + "（空目录）"
        lines = [("[DIR]  " if is_dir else "[FILE] ") + name for is_dir, name in entries]
        return header + "：\n" + "\n".join(lines)

    # ------------------------------------------------------------------
    # 文件信息
    # ------------------------------------------------------------------
    def get_file_type(self, path: str) -> str:
        """获取文件的类型信息。"""
        target = Path(path)
        if not target.is_file():
            raise ToolError("文件不存在：%s" % path)

        extension = target.suffix
        mime, _ = mimetypes.guess_type(str(target))
        _, error = self._read_text(target)
        return "文件 %s\n扩展名：%s\nMIME 类型：%s\n是否纯文本：%s" % (
            target.resolve(),
            extension or "（无）",
            mime or "application/octet-stream",
            "是" if error is None else "否",
        )

    def read_file(self, path: str) -> str:
        """读取纯文本文件内容。"""
        target = Path(path)
        if not target.is_file():
            raise ToolError("文件不存在：%s" % path)

        text, error = self._read_text(target)
        if error is not None:
            raise ToolError(error)

        size = target.stat().st_size
        if len(text) > self.max_read_chars:
            return "文件 %s（%d 字节）内容过长，仅返回前 %d 字符：\n%s" % (
                path,
                size,
                self.max_read_chars,
                text[: self.max_read_chars],
            )
        return "文件 %s（%d 字节）内容：\n%s" % (path, size, text)

    # ------------------------------------------------------------------
    # 文件写入
    # ------------------------------------------------------------------
    def create_file(self, directory: str, filename: str, content: str = "") -> str:
        """在指定目录创建文件（目录不存在时自动创建）。"""
        if not directory:
            raise ToolError("directory 不能为空")
        if not filename:
            raise ToolError("filename 不能为空")
        if any(separator and separator in filename for separator in ("/", "\\")):
            raise ToolError("filename 中不能包含路径分隔符，请把目录写在 directory 参数中")

        folder = Path(directory)
        target = folder / filename
        if folder.is_dir() and target.exists():
            raise ToolError("文件已存在，未覆盖：%s" % target)

        folder.mkdir(parents=True, exist_ok=True)
        data = content or ""
        target.write_text(data, encoding="utf-8", newline="\n")
        return "已创建文件 %s（%d 字符）" % (target.resolve(), len(data))

    def edit_file(self, path: str, old_text: str, new_text: str, replace_all: bool = False) -> str:
        """把文件中的 old_text 替换为 new_text。"""
        target = Path(path)
        if not target.is_file():
            raise ToolError("文件不存在：%s" % path)

        text, error = self._read_text(target)
        if error is not None:
            raise ToolError(error)
        if old_text == "":
            raise ToolError("old_text 不能为空；如需覆盖整个文件内容请先说明")

        count = text.count(old_text)
        if count == 0:
            raise ToolError("在文件 %s 中未找到 old_text" % path)

        if replace_all:
            new_content = text.replace(old_text, new_text)
        else:
            new_content = text.replace(old_text, new_text, 1)
            count = 1

        target.write_text(new_content, encoding="utf-8", newline="\n")
        return "已编辑文件 %s，替换 %d 处" % (target.resolve(), count)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    def _read_text(self, target: Path) -> Tuple[Optional[str], Optional[str]]:
        """读取文本内容；二进制文件返回 (None, 错误描述)。"""
        try:
            raw = target.read_bytes()
        except OSError as exc:
            return None, "读取文件失败：%s" % exc
        if b"\x00" in raw:
            return None, "文件不是纯文本格式（含二进制内容）：%s" % target
        return _decode(raw), None


def _decode(raw: bytes) -> str:
    """按常见编码尝试解码，失败时用 replace 兜底。"""
    for encoding in ("utf-8", "gbk", sys.getfilesystemencoding()):
        if not encoding:
            continue
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")
