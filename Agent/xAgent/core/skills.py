# -*- coding: utf-8 -*-
"""Skill 发现与注册。

规则（见项目文档）：
- 以程序启动时的工作目录为项目根目录，寻找 `.agents\\skills\\` 目录；
- 扫描其中的各个 Skill 子目录；
- 每个 Skill 子目录至少包含一个 SKILL.md，其开头通过 YAML Frontmatter
  声明 name 和 description 两个必需字段；
- 初始化阶段仅加载各 Skill 的 name 和 description，不读取完整 Skill 正文。

容错约定：单个 Skill 目录缺失文件、编码损坏或 frontmatter 字段不全时，
跳过该目录并记录日志，不中断其余 Skill 的发现。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

SKILLS_DIRNAME = ".agents"
SKILLS_SUBDIR = "skills"
SKILL_FILE = "SKILL.md"


@dataclass
class Skill:
    """一个 Skill 的注册信息（初始化阶段只加载 name/description）。"""

    name: str
    description: str
    path: Path

    def to_prompt_block(self) -> str:
        return "- %s：%s" % (self.name, self.description)


class SkillDiscoveryError(Exception):
    """Skill 发现或解析失败（保留以兼容历史调用方；discover_skills 内部不再抛出）。"""


def _parse_frontmatter(text: str) -> dict:
    """解析 SKILL.md 开头的 YAML Frontmatter，仅提取 name / description。

    支持单行值，以及 ``|`` / ``>`` 折叠块（后续缩进行合并为一段）。
    解析失败时返回已能提取的部分，不抛异常。
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}

    data: dict = {}
    i = 1
    while i < end:
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            i += 1
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()

        # 折叠块：value 为 | / > 及其保留/去空白变体时，合并后续缩进行。
        if value in ("|", ">", "|-", ">-", "|+", ">+", "| -", "> -"):
            block: List[str] = []
            j = i + 1
            while j < end:
                nxt = lines[j]
                if nxt.strip() == "":
                    j += 1
                    continue
                if nxt.startswith((" ", "\t")):
                    block.append(nxt.strip())
                    j += 1
                else:
                    break
            value = " ".join(x for x in block if x)
            i = j
        else:
            value = value.strip('"').strip("'")
            i += 1

        if key in ("name", "description"):
            data[key] = value
    return data


def discover_skills(project_root: Optional[str] = None) -> List[Skill]:
    """扫描项目根目录下的 .agents\\skills\\，返回各 Skill 的注册信息。

    项目根目录默认取调用方工作目录（Path.cwd()）。单个目录解析失败时跳过，
    不影响其余 Skill。
    """
    root = Path(project_root) if project_root else Path.cwd()
    skills_dir = root / SKILLS_DIRNAME / SKILLS_SUBDIR

    if not skills_dir.is_dir():
        return []

    skills: List[Skill] = []
    for subdir in sorted(skills_dir.iterdir()):
        if not subdir.is_dir():
            continue
        skill_file = subdir / SKILL_FILE
        if not skill_file.is_file():
            logger.warning("跳过 Skill 目录 %s：缺少 %s", subdir.name, SKILL_FILE)
            continue
        try:
            text = skill_file.read_text(encoding="utf-8")
            meta = _parse_frontmatter(text)
            name = meta.get("name", "").strip()
            description = meta.get("description", "").strip()
            if not name or not description:
                logger.warning(
                    "跳过 Skill %s：frontmatter 缺少 name 或 description", subdir.name
                )
                continue
            skills.append(Skill(name=name, description=description, path=skill_file))
        except (OSError, ValueError) as exc:
            logger.warning("跳过 Skill %s：%s", subdir.name, exc)
            continue

    return skills


def build_skills_prompt(skills: List[Skill]) -> str:
    """把已发现的 Skill 列表拼进系统提示，让模型感知可用的技能。"""
    if not skills:
        return ""
    lines = ["已加载的 Skill："]
    lines.extend(s.to_prompt_block() for s in skills)
    return "\n".join(lines)


__all__ = ["Skill", "SkillDiscoveryError", "build_skills_prompt", "discover_skills"]
