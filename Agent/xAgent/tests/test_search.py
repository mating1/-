# -*- coding: utf-8 -*-
"""网络搜索服务单测：缺配置报错、响应解析与结果格式化。"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.errors import ToolError  # noqa: E402
from core.tools.search import SearchService  # noqa: E402


def test_search_without_endpoint_raises_clear_error():
    svc = SearchService(endpoint="", api_key="")
    try:
        svc.search("八字命理")
    except ToolError as exc:
        assert "未配置搜索服务" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("缺配置应抛 ToolError")


def test_extract_items_supports_common_shapes():
    assert SearchService._extract_items({"items": [{"title": "a"}]}) == [{"title": "a"}]
    assert SearchService._extract_items({"results": [{"title": "b"}]}) == [{"title": "b"}]
    web = {"webPages": {"value": [{"title": "c"}]}}
    assert SearchService._extract_items(web) == [{"title": "c"}]
    assert SearchService._extract_items({}) == []


def test_search_formats_results():
    svc = SearchService(endpoint="https://search.example.test/api", api_key="k")
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "items": [
            {"title": "结果一", "url": "https://a.test", "snippet": "摘要一"},
            {"title": "结果二", "link": "https://b.test", "description": "摘要二"},
        ]
    }
    with patch("core.tools.search.service.requests.get", return_value=fake_resp) as mock_get:
        out = svc.search("塔罗")
    mock_get.assert_called_once()
    assert "结果一" in out and "https://a.test" in out
    assert "结果二" in out and "摘要二" in out


def test_search_non_200_raises():
    svc = SearchService(endpoint="https://search.example.test/api")
    fake_resp = MagicMock()
    fake_resp.status_code = 500
    fake_resp.text = "boom"
    with patch("core.tools.search.service.requests.get", return_value=fake_resp):
        try:
            svc.search("x")
        except ToolError as exc:
            assert "HTTP 500" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("非 200 应抛 ToolError")
