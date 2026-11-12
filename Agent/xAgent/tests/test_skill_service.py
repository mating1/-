# -*- coding: utf-8 -*-
"""技能创建落盘、重名/覆盖校验与加载截断单测。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.errors import ToolError  # noqa: E402
from core.tools.skills import SkillService  # noqa: E402


def test_create_skill_writes_frontmatter_and_registers(tmp_path):
    svc = SkillService(str(tmp_path))
    result = svc.create_skill("my-skill", "一个示例技能", "## 用法\n示例正文")
    assert "已创建 Skill" in result

    folder = tmp_path / ".agents" / "skills" / "my-skill"
    body = (folder / "SKILL.md").read_text(encoding="utf-8")
    assert "name: my-skill" in body
    assert 'description: "一个示例技能"' in body
    assert "示例正文" in body
    assert "my-skill" in svc.names
    assert "示例正文" in svc.load_skill("my-skill")


def test_create_skill_rejects_duplicate_and_overwrite(tmp_path):
    svc = SkillService(str(tmp_path))
    svc.create_skill("dup", "首个技能")

    try:
        svc.create_skill("dup", "第二个技能")
    except ToolError as exc:
        assert "已存在" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("重名技能应被拒绝")

    # 目录存在但未登记时同样拒绝覆盖
    folder = tmp_path / ".agents" / "skills" / "raw"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text("---\nname: raw\n---\n", encoding="utf-8")
    try:
        svc.create_skill("raw", " another")
    except ToolError as exc:
        assert "已存在" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("已有目录应被拒绝覆盖")


def test_create_skill_rejects_invalid_name(tmp_path):
    svc = SkillService(str(tmp_path))
    for bad in ("", "a/b", "a b", "a\\b"):
        try:
            svc.create_skill(bad, "描述")
        except ToolError:
            continue
        raise AssertionError("非法名称应被拒绝：%r" % bad)


def test_load_skill_truncates_long_content(tmp_path):
    svc = SkillService(str(tmp_path))
    svc.create_skill("long", "长技能", "x" * 30000)
    text = svc.load_skill("long")
    assert "过长" in text
    assert len(text) < 30000
