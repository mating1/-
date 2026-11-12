# -*- coding: utf-8 -*-
"""Skill 加载服务：按需读取 SKILL.md 完整正文及引用的附加文件。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from ...errors import ToolError
from ...skills import SKILL_FILE, SKILLS_DIRNAME, SKILLS_SUBDIR, Skill, discover_skills

MAX_SKILL_CHARS = 20000
_NAME_RE = re.compile(r"^[A-Za-z0-9_\-\u4e00-\u9fa5]+$")


class SkillService:
    """基于发现结果提供按名加载与创建能力。"""

    def __init__(self, project_root: str = None) -> None:
        self._project_root = Path(project_root).resolve() if project_root else Path.cwd()
        self._skills_dir = self._project_root / SKILLS_DIRNAME / SKILLS_SUBDIR
        self._skills: Dict[str, Skill] = {
            s.name: s for s in discover_skills(project_root)
        }

    @property
    def names(self) -> list:
        return sorted(self._skills)

    def load_skill(self, name: str) -> str:
        skill = self._skills.get(name)
        if skill is None:
            return "未知 Skill：%s（可用：%s）" % (name, ", ".join(self.names) or "无")
        try:
            text = skill.path.read_text(encoding="utf-8")
        except OSError as exc:
            return "读取 Skill %s 失败：%s" % (name, exc)
        if len(text) > MAX_SKILL_CHARS:
            return "Skill %s 内容过长，仅返回前 %d 字符：\n%s" % (
                name,
                MAX_SKILL_CHARS,
                text[:MAX_SKILL_CHARS],
            )
        return text

    def create_skill(self, name: str, description: str, content: str = "") -> str:
        """在 .agents/skills 下新建技能目录与 SKILL.md，拒绝重名与覆盖。"""
        name = (name or "").strip()
        description = (description or "").strip()
        if not name:
            raise ToolError("name 不能为空")
        if not description:
            raise ToolError("description 不能为空")
        if not _NAME_RE.match(name):
            raise ToolError("name 只能包含中英文、数字、下划线或连字符，不能含路径分隔符或空格")
        if name in self._skills:
            raise ToolError("Skill 已存在，拒绝覆盖：%s" % name)

        folder = self._skills_dir / name
        if folder.exists():
            raise ToolError("Skill 目录已存在，拒绝覆盖：%s" % folder)

        folder.mkdir(parents=True, exist_ok=True)
        skill_file = folder / SKILL_FILE
        safe_desc = description.replace('"', "'")
        body = (
            "---\n"
            "name: %s\n"
            'description: "%s"\n'
            "---\n\n"
            "%s\n"
        ) % (name, safe_desc, content or "")
        skill_file.write_text(body, encoding="utf-8", newline="\n")

        self._skills[name] = Skill(name=name, description=description, path=skill_file)
        return "已创建 Skill %s：%s" % (name, skill_file)

    def load_skill_file(self, name: str, filename: str = "") -> str:
        """按 filename 加载 Skill 附加文件，不重复加载 SKILL.md。

        兼容绝对路径、项目相对路径、相对 Skill 目录路径（精确匹配优先）；
        仅提供文件名时递归搜索，唯一命中才读取，多个同名返回候选路径。
        读取范围限制在 Skill 目录内部。
        """
        skill = self._skills.get(name)
        if skill is None:
            return "未知 Skill：%s（可用：%s）" % (name, ", ".join(self.names) or "无")
        if not filename:
            return "filename 不能为空（仅加载 SKILL.md 时不要传 filename）"

        folder = skill.path.parent.resolve()
        target = self._resolve_target(folder, filename)
        if isinstance(target, list):
            return "存在多个同名文件，请选择路径：\n" + "\n".join(
                "- %s" % p for p in target
            )
        if target is None:
            return "Skill %s 下未找到文件：%s" % (name, filename)

        if not target.is_relative_to(folder):
            return "不允许读取 Skill 目录之外的文件：%s" % target
        try:
            text = target.read_text(encoding="utf-8")
        except OSError as exc:
            return "读取失败：%s" % exc
        if len(text) > MAX_SKILL_CHARS:
            return "Skill %s 的附加文件 %s 内容过长，仅返回前 %d 字符：\n%s" % (
                name,
                target.name,
                MAX_SKILL_CHARS,
                text[:MAX_SKILL_CHARS],
            )
        return text

    # ------------------------------------------------------------------
    def _resolve_target(self, folder: Path, filename: str):
        """解析目标文件；返回 Path / 候选列表 / None。"""
        root = self._project_root
        raw = Path(filename)

        # 1) 精确路径匹配：绝对路径、项目相对路径、Skill 目录相对路径
        candidates = []
        if raw.is_absolute():
            candidates.append(raw.resolve())
        else:
            candidates.append((root / raw).resolve())
            candidates.append((folder / raw).resolve())
        for cand in candidates:
            if cand.is_file():
                return cand

        # 2) 仅文件名 → 递归搜索 Skill 目录
        if not any(sep in filename for sep in ("/", "\\")):
            matches: List[Path] = []
            for hit in folder.rglob(filename):
                if hit.is_file():
                    matches.append(hit.resolve())
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                return matches
        return None
