import logging
import json
from typing import Any
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    # 需要脱敏的字段：camelCase 与 snake_case 两种写法都必须覆盖
    SENSITIVE_EXACT = {"ownerAddr", "owner_addr", "chipNo", "chip_no"}
    SENSITIVE_SUFFIXES = ("Phone", "_phone")

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "tool_name"):
            payload["tool_name"] = record.tool_name
        if hasattr(record, "params"):
            payload["params"] = self._sanitize(record.params)
        if hasattr(record, "status"):
            payload["status"] = record.status
        if hasattr(record, "duration_ms"):
            payload["duration_ms"] = record.duration_ms
        return json.dumps(payload, ensure_ascii=False)

    @classmethod
    def _is_sensitive(cls, key: str) -> bool:
        return key in cls.SENSITIVE_EXACT or key.endswith(cls.SENSITIVE_SUFFIXES)

    @classmethod
    def _sanitize(cls, value: Any) -> Any:
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, item in value.items():
                if cls._is_sensitive(str(key)):
                    result[key] = "[REDACTED]"
                else:
                    result[key] = cls._sanitize(item)
            return result
        if isinstance(value, list):
            return [cls._sanitize(item) for item in value]
        return value


def configure_logging() -> None:
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
