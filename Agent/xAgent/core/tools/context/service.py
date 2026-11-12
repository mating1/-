# -*- coding: utf-8 -*-
"""recallContext 工具的服务实现：本地全文关键词检索。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional


class ContextSearchService:
    """在归档目录（默认 ``.agents/context/*.jsonl``）做本地全文关键词检索。"""

    def __init__(
        self,
        project_root: str = ".",
        archive_dirname: str = ".agents/context",
        limit: int = 8,
        snippet: int = 240,
    ) -> None:
        self.archive_dir = (
            Path(project_root).expanduser().resolve().joinpath(*Path(archive_dirname).parts)
        )
        self.limit = int(limit or 8)
        self.snippet = int(snippet or 240)

    def recall(self, id: str = "", text: str = "", limit: Optional[int] = None) -> str:
        keyword = (text or "").strip()
        if not keyword:
            return "参数 text 不能为空：请提供需要查找的关键词或文本。"
        limit = int(limit or self.limit)

        if id:
            target = self.archive_dir / ("%s.jsonl" % id.strip())
            if not target.is_file():
                return "未找到编号为 %s 的归档文件。" % id
            targets = [target]
        else:
            targets = sorted(self.archive_dir.glob("*.jsonl")) if self.archive_dir.is_dir() else []

        if not targets:
            return "尚未生成任何上下文归档，暂无可检索内容。"

        hits: List[str] = []
        for path in targets:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError as exc:
                hits.append("[%s] 读取失败：%s" % (path.stem, exc))
                continue
            for line_no, line in enumerate(lines, start=1):
                if keyword.lower() not in line.lower():
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                role = record.get("role", "?")
                content = re.sub(r"\s+", " ", str(record.get("content", ""))).strip()
                if len(content) > self.snippet:
                    content = content[: self.snippet] + "…"
                hits.append("[归档 %s · 第 %d 行 · %s] %s" % (path.stem, line_no, role, content))
                if len(hits) >= limit:
                    break
            if len(hits) >= limit:
                break

        if not hits:
            return "未找到包含“%s”的历史内容。" % keyword
        return (
            "在 %d 个归档文件中检索到以下片段（最多 %d 条，内容已截断）：\n\n%s"
            % (len(targets), limit, "\n".join(hits))
        )
