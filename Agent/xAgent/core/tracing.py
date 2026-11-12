# -*- coding: utf-8 -*-
"""统一的调用追踪日志。

一次工具调用产出一行 JSON，含工具名、参数、状态、耗时与错误摘要，
便于事后排查"模型到底调了什么、慢在哪里、失败在哪一步"。

设计约束：
- 仅用标准库，core 层不引入第三方日志框架；
- 日志落盘失败绝不能影响主流程（写日志的异常一律吞掉）；
- 参数里的密钥类字段在写盘前递归脱敏。
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

LOGGER_NAME = "xagent"
LOG_DIRNAME = Path(".agents") / "logs"
LOG_FILENAME = "xagent.log"
SENSITIVE_KEYS = {"api_key", "apikey", "authorization", "token", "password", "secret"}


def _redact(value: Any, depth: int = 0) -> Any:
    """递归脱敏：命中密钥类键名时替换为 [REDACTED]。"""
    if depth > 6:
        return "..."
    if isinstance(value, dict):
        result: Dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                result[key] = "[REDACTED]"
            else:
                result[key] = _redact(item, depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [_redact(item, depth + 1) for item in value]
    if isinstance(value, str) and len(value) > 200:
        return value[:200] + "...(截断)"
    return value


class JsonLineFormatter(logging.Formatter):
    """输出单行 JSON：时间、级别、事件、工具、状态、耗时。"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created).astimezone().isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
        }
        for field in ("tool_name", "status", "duration_ms", "detail"):
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        return json.dumps(payload, ensure_ascii=False)


_configured = False


def configure(workspace: str = None, level: int = logging.INFO) -> logging.Logger:
    """初始化追踪日志（幂等）；落盘到 <workspace>/.agents/logs/xagent.log。"""
    global _configured
    logger = logging.getLogger(LOGGER_NAME)
    if _configured:
        return logger

    logger.setLevel(level)
    logger.propagate = False
    formatter = JsonLineFormatter()

    stream_handler = logging.StreamHandler(stream=sys.stderr)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    try:
        log_dir = Path(workspace or Path.cwd()) / LOG_DIRNAME
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            log_dir / LOG_FILENAME, encoding="utf-8", delay=True
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # 目录不可写时只保留 stderr，不影响运行
        pass

    _configured = True
    return logger


def record_tool_call(
    tool_name: str,
    status: str,
    duration_ms: float,
    detail: Any = None,
) -> None:
    """记录一次工具调用；任何异常都不外抛。"""
    try:
        logger = logging.getLogger(LOGGER_NAME)
        logger.info(
            "tool call %s" % tool_name,
            extra={
                "event": "tool_call",
                "tool_name": tool_name,
                "status": status,
                "duration_ms": round(float(duration_ms), 2),
                "detail": _redact(detail),
            },
        )
    except Exception:  # noqa: BLE001 - 记日志失败不得影响业务
        pass


def log_path(workspace: str = None) -> str:
    """返回日志文件的绝对路径（用于文档与状态展示）。"""
    return os.path.join(str(Path(workspace or Path.cwd()) / LOG_DIRNAME), LOG_FILENAME)


__all__ = ["configure", "record_tool_call", "log_path", "JsonLineFormatter"]
