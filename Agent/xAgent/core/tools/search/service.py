# -*- coding: utf-8 -*-
"""网络搜索服务：调用可配置的搜索服务 API，返回结构化结果列表。

搜索后端地址与密钥走环境变量注入，不硬编码；未配置时抛出清晰错误，
由工具层回填给模型，便于模型告知用户需要补配置。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import requests

from ...errors import ToolError

DEFAULT_TIMEOUT = 15
DEFAULT_MAX_RESULTS = 8


class SearchService:
    """通过 HTTP 调用外部搜索 API。"""

    def __init__(
        self,
        endpoint: str = None,
        api_key: str = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_results: int = DEFAULT_MAX_RESULTS,
    ) -> None:
        self.endpoint = (endpoint or os.environ.get("XAGENT_SEARCH_ENDPOINT", "")).strip().rstrip("/")
        self.api_key = (api_key or os.environ.get("XAGENT_SEARCH_API_KEY", "")).strip()
        self.timeout = timeout
        self.max_results = max_results

    def search(self, query: str) -> str:
        if not query or not query.strip():
            raise ToolError("query 不能为空")
        if not self.endpoint:
            raise ToolError(
                "未配置搜索服务：请设置环境变量 XAGENT_SEARCH_ENDPOINT"
                "（按需设置 XAGENT_SEARCH_API_KEY）后再使用网络搜索"
            )

        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer %s" % self.api_key
        params = {"q": query.strip(), "count": self.max_results}

        try:
            resp = requests.get(
                self.endpoint, params=params, headers=headers, timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise ToolError("搜索服务请求失败：%s" % exc)

        if resp.status_code != 200:
            raise ToolError(
                "搜索服务返回 HTTP %s：%s" % (resp.status_code, resp.text[:200])
            )

        try:
            data = resp.json()
        except ValueError:
            raise ToolError("搜索服务返回的不是合法 JSON")

        items = self._extract_items(data)
        if not items:
            return "未检索到相关结果：%s" % query

        lines = ["搜索「%s」，共 %d 条结果：" % (query.strip(), len(items))]
        for idx, item in enumerate(items, 1):
            title = item.get("title") or "（无标题）"
            url = item.get("url") or item.get("link") or ""
            snippet = item.get("snippet") or item.get("description") or ""
            lines.append("%d. %s\n   %s\n   %s" % (idx, title, url, snippet))
        return "\n".join(lines)

    @staticmethod
    def _extract_items(data: Any) -> List[Dict[str, str]]:
        """从常见搜索响应结构中抽取结果列表。"""
        if not isinstance(data, dict):
            return []
        candidates = (
            data.get("items"),
            data.get("results"),
            (data.get("webPages") or {}).get("value") if isinstance(data.get("webPages"), dict) else None,
        )
        for bucket in candidates:
            if isinstance(bucket, list) and bucket:
                return [dict(item) for item in bucket if isinstance(item, dict)]
        return []
