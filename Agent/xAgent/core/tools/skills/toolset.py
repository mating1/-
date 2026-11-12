# -*- coding: utf-8 -*-
"""loadSkill 工具集。"""

from __future__ import annotations

from typing import List

from ..base import FunctionTool, Tool
from .service import SkillService

TOOL_LOAD_SKILL = "loadSkill"
TOOL_CREATE_SKILL = "createSkill"


def build_skill_tools(service: SkillService = None) -> List[Tool]:
    service = service or SkillService()
    return [
        FunctionTool(
            name=TOOL_CREATE_SKILL,
            description="在技能目录下新建一个技能（目录 + 带 YAML frontmatter 的 SKILL.md）。校验命名合法性与重名，目标已存在时拒绝覆盖；创建后当次会话即可按名加载。",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "技能名称（中英文/数字/下划线/连字符）"},
                    "description": {"type": "string", "description": "技能用途与触发场景，会注入系统提示"},
                    "content": {"type": "string", "description": "可选：写入 SKILL.md 正文的使用说明"},
                },
                "required": ["name", "description"],
            },
            func=lambda name, description, content="": service.create_skill(name, description, content),
        ),
        FunctionTool(
            name=TOOL_LOAD_SKILL,
            description="按需加载某个 Skill 的说明。仅提供 name 时返回该 Skill 的 SKILL.md 全文；同时提供 filename 时返回对应附加文件（不加载 SKILL.md）。filename 支持相对 Skill 目录的路径、项目相对路径、绝对路径或仅文件名（唯一命中时读取，多个同名返回候选路径）。文件读取限制在 Skill 目录内部。",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "要加载的 Skill 名称（必需）"},
                    "filename": {
                        "type": "string",
                        "description": "可选：要加载的 Skill 文件路径或名称；不填则返回 SKILL.md 全文",
                    },
                },
                "required": ["name"],
            },
            func=lambda name, filename="": (
                service.load_skill_file(name, filename)
                if filename
                else service.load_skill(name)
            ),
        ),
    ]
