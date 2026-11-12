# -*- coding: utf-8 -*-
"""文件系统业务服务。

这一层只做"文件操作"这件事：错误通过 ToolError 抛出，
不关心调用者是谁（模型 / 测试 / 未来的其他前端）。

边界约定：构造时若传入 ``root``（工作目录），所有相对路径都解析到该目录下，
解析结果越出 ``root`` 即拒绝；``root`` 为空时不做边界校验（兼容旧用法与测试）。
"""

from __future__ import annotations

import mimetypes
import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from ...errors import ToolError

DEFAULT_MAX_READ_CHARS = 50000


def _is_within(root: Path, target: Path) -> bool:
    """target 是否位于 root 之内（含 root 本身）。"""
    try:
        target.relative_to(root)
        return True
    except ValueError:
        return False


class FileSystemService:
    """基于本地磁盘的文件系统服务。"""

    def __init__(
        self,
        root: Optional[str] = None,
        max_read_chars: int = DEFAULT_MAX_READ_CHARS,
        strict_root: bool = False,
    ) -> None:
        self.root = Path(root).expanduser().resolve() if root else None
        self.max_read_chars = max_read_chars
        self.strict_root = strict_root

    # ------------------------------------------------------------------
    # 路径解析与边界保护
    # ------------------------------------------------------------------
    def _resolve(self, path: str) -> Path:
        """把入参路径解析为绝对路径，并校验不越出工作目录。"""
        if not path or not str(path).strip():
            raise ToolError("路径不能为空")
        candidate = Path(str(path)).expanduser()
        if self.root is not None:
            if not candidate.is_absolute():
                candidate = self.root / candidate
            candidate = candidate.resolve()
            if not _is_within(self.root, candidate):
                raise ToolError("禁止访问工作目录之外的路径：%s" % path)
            return candidate
        if self.strict_root:
            raise ToolError("未配置工作目录 root，拒绝宽松路径访问：%s" % path)
        return candidate.resolve()

    # ------------------------------------------------------------------
    # 目录
    # ------------------------------------------------------------------
    def get_cwd(self) -> str:
        """获取当前工作目录。"""
        return str(self.root if self.root is not None else Path.cwd())

    def list_dir(self, path: str = ".") -> str:
        """列出目录下的所有文件和子目录。"""
        target = self._resolve(path or ".")
        if not target.is_dir():
            raise ToolError("目录不存在：%s" % path)

        entries: List[Tuple[bool, str]] = []
        with os.scandir(str(target)) as iterator:
            for entry in iterator:
                entries.append((entry.is_dir(), entry.name))
        entries.sort(key=lambda item: (not item[0], item[1].lower()))

        header = "目录 %s，共 %d 项" % (target, len(entries))
        if not entries:
            return header + "（空目录）"
        lines = [("[DIR]  " if is_dir else "[FILE] ") + name for is_dir, name in entries]
        return header + "：\n" + "\n".join(lines)

    def create_dir(self, path: str, parents: bool = True, exist_ok: bool = False) -> str:
        """创建目录，支持多级父目录；已存在时按 exist_ok 决定是否报错。"""
        target = self._resolve(path)
        if target.exists():
            if not target.is_dir():
                raise ToolError("路径已存在且不是目录：%s" % path)
            if exist_ok:
                return "目录已存在：%s" % target
            raise ToolError("目录已存在，未重复创建：%s" % target)
        target.mkdir(parents=bool(parents), exist_ok=False)
        return "已创建目录 %s" % target

    def delete_dir(self, path: str, recursive: bool = False) -> str:
        """删除目录；默认拒绝删除非空目录，显式 recursive 才递归清理。"""
        target = self._resolve(path)
        if not target.is_dir():
            raise ToolError("目录不存在：%s" % path)
        if any(target.iterdir()) and not recursive:
            raise ToolError("目录非空，拒绝删除；确需递归删除请显式指定 recursive=true：%s" % path)
        if recursive:
            shutil.rmtree(target)
        else:
            target.rmdir()
        return "已删除目录 %s" % target

    # ------------------------------------------------------------------
    # 文件信息
    # ------------------------------------------------------------------
    def get_file_type(self, path: str) -> str:
        """获取路径类型：文件 / 目录 / 符号链接，附扩展名与 MIME。"""
        target = self._resolve(path)
        if not target.exists():
            raise ToolError("路径不存在：%s" % path)

        if target.is_symlink():
            kind = "符号链接"
        elif target.is_dir():
            kind = "目录"
        elif target.is_file():
            kind = "文件"
        else:
            kind = "其他类型"

        extension = target.suffix
        mime, _ = mimetypes.guess_type(str(target))
        plain_text = "不适用"
        if target.is_file():
            _, error = self._read_text(target)
            plain_text = "是" if error is None else "否"
        return "路径 %s\n类型：%s\n扩展名：%s\nMIME 类型：%s\n是否纯文本：%s" % (
            target,
            kind,
            extension or "（无）",
            mime or "application/octet-stream",
            plain_text,
        )

    def read_file(self, path: str) -> str:
        """读取纯文本文件内容。"""
        target = self._resolve(path)
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

        folder = self._resolve(directory)
        target = folder / filename
        if folder.is_dir() and target.exists():
            raise ToolError("文件已存在，未覆盖：%s" % target)

        folder.mkdir(parents=True, exist_ok=True)
        data = content or ""
        target.write_text(data, encoding="utf-8", newline="\n")
        return "已创建文件 %s（%d 字符）" % (target, len(data))

    def edit_file(self, path: str, old_text: str, new_text: str, replace_all: bool = False) -> str:
        """把文件中的 old_text 替换为 new_text。"""
        target = self._resolve(path)
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
        return "已编辑文件 %s，替换 %d 处" % (target, count)

    def delete_file(self, path: str) -> str:
        """删除单个文件，拒绝删除目录。"""
        target = self._resolve(path)
        if not target.exists():
            raise ToolError("文件不存在：%s" % path)
        if target.is_dir():
            raise ToolError("目标是目录，请使用删除目录工具：%s" % path)
        target.unlink()
        return "已删除文件 %s" % target

    def rename_move(self, source: str, destination: str) -> str:
        """重命名或移动文件 / 目录；目标已存在时拒绝覆盖。"""
        if not source or not destination:
            raise ToolError("source 与 destination 不能为空")
        src = self._resolve(source)
        dst = self._resolve(destination)
        if not src.exists():
            raise ToolError("源路径不存在：%s" % source)
        if dst.exists():
            raise ToolError("目标已存在，未覆盖：%s" % destination)
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        return "已移动/重命名 %s → %s" % (src, dst)

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
