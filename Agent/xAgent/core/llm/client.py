# -*- coding: utf-8 -*-
"""OpenAI 兼容接口的流式客户端。

只做三件事：构造请求、解析 SSE、输出增量；不含任何业务与界面逻辑。
"""

from __future__ import annotations

import json
import warnings
from typing import Any, AsyncIterator, Iterator, List, Optional

# requests 的版本检查告警在本机属于误报，不影响功能（需在 import requests 之前设置）
warnings.filterwarnings("ignore", message=".*doesn't match a supported version.*")

import requests  # noqa: E402

from ..config import LLMConfig  # noqa: E402
from ..errors import LLMError  # noqa: E402
from ..models import Message  # noqa: E402
from ..utils.asyncbridge import iterate_in_thread  # noqa: E402
from .deltas import LLMDelta, ToolCallDelta  # noqa: E402
from .protocol import BaseLLMClient  # noqa: E402


class LLMClient(BaseLLMClient):
    """基于 ``requests`` 的 OpenAI 兼容流式客户端。"""

    def __init__(
        self,
        config: LLMConfig,
        tool_schemas: Optional[List[dict]] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        super().__init__(tool_schemas)
        self.config = config
        self.model = config.model
        self._session = session or requests.Session()

    # ------------------------------------------------------------------
    # 同步接口
    # ------------------------------------------------------------------
    def stream(self, messages: List[Message]) -> Iterator[LLMDelta]:
        """发起一次流式对话，逐个返回响应增量。"""
        payload = self._payload(messages)
        try:
            response = self._session.post(
                self.config.endpoint,
                headers=self._headers(),
                json=payload,
                stream=True,
                timeout=self.config.timeout,
            )
        except requests.RequestException as exc:
            raise LLMError("请求大模型接口失败：%s" % exc) from exc

        if response.status_code != 200:
            detail = response.text[:300]
            raise LLMError("大模型接口返回 HTTP %s：%s" % (response.status_code, detail))

        # SSE 响应头不带 charset，requests 会按 ISO-8859-1 解码，这里强制 UTF-8
        response.encoding = "utf-8"
        try:
            for line in response.iter_lines(decode_unicode=True):
                if isinstance(line, str) and line.startswith("data:"):
                    if line[5:].strip() == "[DONE]":
                        break
                delta = self._parse_line(line)
                if delta is not None:
                    yield delta
        except requests.RequestException as exc:
            raise LLMError("读取流式响应失败：%s" % exc) from exc
        finally:
            response.close()

    # ------------------------------------------------------------------
    # 异步接口
    # ------------------------------------------------------------------
    def astream(self, messages: List[Message]) -> AsyncIterator[LLMDelta]:
        """异步版本的流式对话（内部在工作线程执行同步请求）。"""
        return iterate_in_thread(lambda: self.stream(messages))

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    def _headers(self) -> dict:
        return {
            "Authorization": "Bearer " + self.config.api_key,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _parse_line(line: Any) -> Optional[LLMDelta]:
        """解析一行 SSE 数据，非法数据返回 None（跳过）。"""
        if not line or not isinstance(line, str):
            return None
        if not line.startswith("data:"):
            return None
        data = line[5:].strip()
        if not data or data == "[DONE]":
            return None
        try:
            chunk = json.loads(data)
            choice = (chunk.get("choices") or [{}])[0]
            raw_delta = choice.get("delta") or {}
        except (ValueError, IndexError, TypeError, AttributeError):
            return None

        tool_deltas: List[ToolCallDelta] = []
        for raw_call in raw_delta.get("tool_calls") or []:
            function = raw_call.get("function") or {}
            tool_deltas.append(
                ToolCallDelta(
                    index=int(raw_call.get("index", 0) or 0),
                    id=raw_call.get("id") or "",
                    name=function.get("name") or "",
                    arguments=function.get("arguments") or "",
                )
            )

        return LLMDelta(
            content=raw_delta.get("content") or "",
            tool_calls=tuple(tool_deltas),
            finish_reason=choice.get("finish_reason"),
            raw=chunk,
        )
