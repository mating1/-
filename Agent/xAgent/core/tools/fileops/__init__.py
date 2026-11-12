# -*- coding: utf-8 -*-
"""文件系统工具集。

- ``service``：纯业务逻辑，不认识"工具""模型""界面"这些概念；
- ``toolset``：把 service 的方法包装成模型可调用的工具。

由 chat-tool-fileops.py 改造而来，把原先耦合在一起的工具定义、
业务实现、调用分发拆成了两个模块。
"""

from .service import FileSystemService
from .toolset import build_file_tools

__all__ = ["FileSystemService", "build_file_tools"]
