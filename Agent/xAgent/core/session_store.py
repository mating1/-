# -*- coding: utf-8 -*-
"""会话存档：把对话历史保存为本地文件，支持列出与恢复。

存档格式为 JSON（一个会话一个文件），便于 TUI 的 /save、/resume 使用，
也承担 AGENTS.md 注入内容的持久化（随消息一起保存）。
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .models import Message, ToolCall


class SessionStore:
    """基于工作区目录的会话存档。"""

    def __init__(self, workspace: str, dirname: str = ".agents/sessions") -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.dir = self.workspace / dirname

    # ------------------------------------------------------------------
    # 保存
    # ------------------------------------------------------------------
    def save(self, messages: List[Message], system_prompt: str = "", title: str = "") -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        session_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = self.dir / ("%s.json" % session_id)
        suffix = 1
        while path.exists():
            suffix += 1
            path = self.dir / ("%s-%d.json" % (session_id, suffix))

        data = {
            "id": path.stem,
            "title": (title or self._guess_title(messages) or "未命名会话").strip(),
            "created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "system_prompt": system_prompt,
            "messages": [self._dump_message(m) for m in messages],
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def set_title(path: Path, title: str) -> None:
        """改写某个存档的标题（会话结束后由模型总结命名时使用）。"""
        target = Path(path)
        if not title:
            return
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        data["title"] = title.strip()[:40]
        try:
            target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _guess_title(messages: List[Message]) -> str:
        for message in messages:
            if message.role == "user" and message.content.strip():
                line = " ".join(message.content.split())
                return line[:40]
        return ""

    @staticmethod
    def _dump_message(message: Message) -> Dict:
        record: Dict = {"role": message.role, "content": message.content}
        if message.tool_calls:
            record["tool_calls"] = [
                {"id": c.id, "name": c.name, "arguments": c.arguments} for c in message.tool_calls
            ]
        if message.tool_call_id:
            record["tool_call_id"] = message.tool_call_id
        if message.name:
            record["name"] = message.name
        return record

    # ------------------------------------------------------------------
    # 列表
    # ------------------------------------------------------------------
    def list(self) -> List[Dict]:
        if not self.dir.is_dir():
            return []
        entries: List[Dict] = []
        for path in sorted(self.dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            entries.append(
                {
                    "id": data.get("id") or path.stem,
                    "title": data.get("title") or "未命名会话",
                    "created": data.get("created") or "",
                    "count": len(data.get("messages") or []),
                    "path": str(path),
                }
            )
        return entries

    # ------------------------------------------------------------------
    # 恢复
    # ------------------------------------------------------------------
    def load(self, session_id: str) -> Tuple[str, List[Message]]:
        path = self.dir / ("%s.json" % session_id)
        if not path.is_file():
            raise FileNotFoundError("会话不存在：%s" % session_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        messages = [self._load_message(m) for m in (data.get("messages") or [])]
        return data.get("system_prompt") or "", messages

    @staticmethod
    def _load_message(record: Dict) -> Message:
        calls = [
            ToolCall(
                id=str(c.get("id") or ""),
                name=str(c.get("name") or ""),
                arguments=str(c.get("arguments") or "{}"),
            )
            for c in (record.get("tool_calls") or [])
        ]
        return Message(
            role=str(record.get("role") or "user"),
            content=str(record.get("content") or ""),
            tool_calls=calls,
            tool_call_id=record.get("tool_call_id"),
            name=record.get("name"),
        )

    def latest(self) -> Optional[Dict]:
        entries = self.list()
        return entries[0] if entries else None


__all__ = ["SessionStore"]
