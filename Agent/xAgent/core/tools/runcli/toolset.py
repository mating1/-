# -*- coding: utf-8 -*-
"""RunCli 工具集。"""

from __future__ import annotations

from typing import List

from ..base import FunctionTool, Tool
from .service import RunCliService

TOOL_RUN_CLI = "RunCli"


def run_cli_tool(service: RunCliService = None) -> List[Tool]:
    service = service or RunCliService()
    return [
        FunctionTool(
            name=TOOL_RUN_CLI,
            description="调用本地已安装的任意命令行程序（CLI）。传入程序名 command 和参数列表 args，通过 subprocess 执行，返回 stdout、stderr 和退出码。用于受控教学实验环境。",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的程序名，例如 dir、python、git、pip"},
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "命令参数列表，不要拼接到 command 里",
                    },
                },
                "required": ["command"],
            },
            func=lambda command, args=None: service.run_cli(command, args or []),
        ),
    ]
