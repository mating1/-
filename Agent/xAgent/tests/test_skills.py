# -*- coding: utf-8 -*-
"""技能发现与 frontmatter 解析的单元测试。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.skills import (  # noqa: E402
    _parse_frontmatter,
    build_skills_prompt,
    discover_skills,
)


def _write_skill(root: Path, dirname: str, body: str) -> Path:
    folder = root / ".agents" / "skills" / dirname
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(body, encoding="utf-8")
    return folder


def test_parse_frontmatter_single_line():
    text = "---\nname: demo-skill\ndescription: 一个示例技能\n---\n正文"
    meta = _parse_frontmatter(text)
    assert meta["name"] == "demo-skill"
    assert meta["description"] == "一个示例技能"


def test_parse_frontmatter_folded_block():
    text = (
        "---\n"
        "name: folded\n"
        "description: |\n"
        "  第一行说明\n"
        "  第二行说明\n"
        "---\n"
        "正文"
    )
    meta = _parse_frontmatter(text)
    assert meta["name"] == "folded"
    assert "第一行说明" in meta["description"]
    assert "第二行说明" in meta["description"]


def test_parse_frontmatter_missing_frontmatter():
    assert _parse_frontmatter("没有 frontmatter 的正文") == {}


def test_discover_skips_bad_dirs(tmp_path):
    _write_skill(
        tmp_path, "good",
        "---\nname: good-skill\ndescription: 正常技能\n---\n正文",
    )
    # 缺 SKILL.md
    (tmp_path / ".agents" / "skills" / "no-file").mkdir(parents=True)
    # 缺 description
    _write_skill(tmp_path, "bad-meta", "---\nname: bad\n---\n正文")

    skills = discover_skills(str(tmp_path))
    names = [s.name for s in skills]
    assert names == ["good-skill"]


def test_discover_empty_root(tmp_path):
    assert discover_skills(str(tmp_path)) == []


def test_build_skills_prompt(tmp_path):
    _write_skill(
        tmp_path, "one",
        "---\nname: one\ndescription: 技能一\n---\n",
    )
    skills = discover_skills(str(tmp_path))
    prompt = build_skills_prompt(skills)
    assert "已加载的 Skill" in prompt
    assert "- one：技能一" in prompt
    assert build_skills_prompt([]) == ""
