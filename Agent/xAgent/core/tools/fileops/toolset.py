# -*- coding: utf-8 -*-
"""文件操作工具集：把 FileSystemService 暴露给模型。

工具名与参数 schema 是"模型契约"，保持与原 chat-tool-fileops.py 一致，
这样既延续了既有的提示词习惯，也方便后续扩展新工具。
"""

from __future__ import annotations

from typing import List

from ..base import FunctionTool, Tool
from .service import FileSystemService

TOOL_GETCWD = "getcwd"
TOOL_LIST_DIR = "listDir"
TOOL_GET_FILE_TYPE = "getFileType"
TOOL_READ_FILE = "readFile"
TOOL_CREATE_FILE = "createFile"
TOOL_EDIT_FILE = "editFile"


def build_file_tools(service: FileSystemService = None) -> List[Tool]:
    """构造文件操作工具列表。"""
    service = service or FileSystemService()

    return [
        FunctionTool(
            name=TOOL_GETCWD,
            description="获取当前工作目录",
            parameters={"type": "object", "properties": {}, "required": []},
            func=lambda **_: service.get_cwd(),
        ),
        FunctionTool(
            name=TOOL_LIST_DIR,
            description="列出指定目录下所有文件和子目录，不传 path 时列出当前工作目录",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "要列出的目录路径"}},
                "required": [],
            },
            func=lambda path=".": service.list_dir(path or "."),
        ),
        FunctionTool(
            name=TOOL_GET_FILE_TYPE,
            description="获取指定文件的文件类型（MIME 类型、扩展名、是否纯文本）",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "文件路径"}},
                "required": ["path"],
            },
            func=lambda path: service.get_file_type(path),
        ),
        FunctionTool(
            name=TOOL_READ_FILE,
            description="获取指定文件的内容，仅支持纯文本格式文件",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "文件路径"}},
                "required": ["path"],
            },
            func=lambda path: service.read_file(path),
        ),
        FunctionTool(
            name=TOOL_CREATE_FILE,
            description="根据指定的目录和文件名创建新文件，可选写入初始内容",
            parameters={
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "文件所在目录路径"},
                    "filename": {"type": "string", "description": "文件名，含扩展名"},
                    "content": {"type": "string", "description": "写入文件的初始内容，默认为空"},
                },
                "required": ["directory", "filename"],
            },
            func=lambda directory, filename, content="": service.create_file(directory, filename, content),
        ),
        FunctionTool(
            name=TOOL_EDIT_FILE,
            description="编辑指定文件的内容（把文件中的 old_text 替换为 new_text），仅支持纯文本格式文件",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "old_text": {"type": "string", "description": "要被替换的原文本"},
                    "new_text": {"type": "string", "description": "替换后的新文本"},
                    "replace_all": {
                        "type": "boolean",
                        "description": "是否替换所有匹配项，默认只替换第一处",
                    },
                },
                "required": ["path", "old_text", "new_text"],
            },
            func=lambda path, old_text, new_text, replace_all=False: service.edit_file(
                path, old_text, new_text, bool(replace_all)
            ),
        ),
    ]
