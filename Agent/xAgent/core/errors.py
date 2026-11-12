# -*- coding: utf-8 -*-
"""核心层统一异常定义。

分层约定：core 层不依赖任何界面框架（Textual / Web / Desktop），
只通过异常与事件对象向外暴露错误信息。
"""

from __future__ import annotations


class CoreError(Exception):
    """core 层异常基类。"""


class ConfigError(CoreError):
    """配置缺失或格式非法。"""


class LLMError(CoreError):
    """调用大模型接口失败（网络异常、非 200 响应、协议解析失败等）。"""


class ToolError(CoreError):
    """工具执行失败。

    工具服务层只抛异常，不关心如何展示；由 ToolRegistry 统一转换为
    可回传给模型的文本结果。
    """
