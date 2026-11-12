# -*- coding: utf-8 -*-
"""AnythingLLM MCP 工具分发与契约单测（不连真实后端）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("ANYTHINGLLM_API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server  # noqa: E402


def test_list_workspaces(monkeypatch):
    def fake(method, path, payload=None, timeout=180):
        return {"workspaces": [{"name": "默认", "slug": "default", "documents": [1, 2]}]}, None

    monkeypatch.setattr(server, "_http_json", fake)
    text, err = server.list_workspaces()
    assert err is None
    assert "default" in text and "2 篇" in text


def test_list_documents(monkeypatch):
    def fake(method, path, payload=None, timeout=180):
        return {"documents": [{"title": "合同.pdf", "docPath": "custom-docs/合同.pdf"}]}, None

    monkeypatch.setattr(server, "_http_json", fake)
    text, err = server.list_documents()
    assert err is None
    assert "合同.pdf" in text and "custom-docs/" in text


def test_add_documents_calls_update_embeddings(monkeypatch):
    calls = []

    def fake(method, path, payload=None, timeout=180):
        calls.append((method, path, payload))
        return {"success": True}, None

    monkeypatch.setattr(server, "_http_json", fake)
    monkeypatch.setattr(server, "WORKSPACE_SLUG", "default")
    text, err = server.add_documents_to_workspace("", ["custom-docs/a.pdf"])
    assert err is None
    assert calls[0][1].endswith("/update-embeddings")
    assert calls[0][2]["adds"] == ["custom-docs/a.pdf"]
    assert "向量化" in text


def test_ask_workspace_returns_text(monkeypatch):
    def fake(method, path, payload=None, timeout=180):
        return {"textResponse": "这是回答"}, None

    monkeypatch.setattr(server, "_http_json", fake)
    monkeypatch.setattr(server, "WORKSPACE_SLUG", "default")
    text, err = server.ask_workspace("胡芳是谁")
    assert err is None and text == "这是回答"


def test_ask_workspace_propagates_error(monkeypatch):
    def fake(method, path, payload=None, timeout=180):
        return None, "AnythingLLM HTTP 500: boom"

    monkeypatch.setattr(server, "_http_json", fake)
    monkeypatch.setattr(server, "WORKSPACE_SLUG", "default")
    text, err = server.ask_workspace("问题")
    assert err is not None and "HTTP 500" in err


def test_dispatch_unknown_tool():
    text, err = server.dispatch("nope", {})
    assert err is not None and "未知工具" in err


def test_upload_local_document_success(monkeypatch, tmp_path):
    f = tmp_path / "合同.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    uploaded = []

    def fake_multipart(path, filename, file_bytes, mime, timeout=180):
        uploaded.append((path, filename, len(file_bytes), mime))
        return {"documents": [{"title": "合同.pdf", "docPath": "custom-docs/合同.pdf"}]}, None

    monkeypatch.setattr(server, "_http_multipart", fake_multipart)
    monkeypatch.setattr(server, "add_documents_to_workspace", lambda slug, docs: ("已加入工作区", None))

    text, err = server.upload_local_document(str(f), "", True)
    assert err is None
    assert uploaded[0][0] == "/api/v1/document/upload"
    assert uploaded[0][2] == len(b"%PDF-1.4 fake")
    assert "custom-docs/合同.pdf" in text and "已加入工作区" in text


def test_upload_missing_file(monkeypatch, tmp_path):
    text, err = server.upload_local_document(str(tmp_path / "nope.pdf"))
    assert err is not None and "不存在" in err


def test_upload_rejects_unsupported_ext(monkeypatch, tmp_path):
    f = tmp_path / "evil.exe"
    f.write_bytes(b"MZ")
    text, err = server.upload_local_document(str(f))
    assert err is not None and "不支持的文件类型" in err


def test_upload_rejects_empty_file(monkeypatch, tmp_path):
    f = tmp_path / "empty.txt"
    f.write_bytes(b"")
    text, err = server.upload_local_document(str(f))
    assert err is not None and "为空" in err


def test_upload_rejects_oversize(monkeypatch, tmp_path):
    f = tmp_path / "big.pdf"
    f.write_bytes(b"x" * (server.MAX_UPLOAD_BYTES + 1))
    text, err = server.upload_local_document(str(f))
    assert err is not None and "超过 50MB" in err


def test_upload_response_without_docpath(monkeypatch, tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("hi", encoding="utf-8")
    monkeypatch.setattr(server, "_http_multipart", lambda *a, **k: ({"documents": [{}]}, None))
    text, err = server.upload_local_document(str(f), add_to_workspace=False)
    assert err is not None and "docPath" in err


def test_upload_skip_add_to_workspace(monkeypatch, tmp_path):
    f = tmp_path / "note.md"
    f.write_text("# hi", encoding="utf-8")
    monkeypatch.setattr(
        server, "_http_multipart",
        lambda *a, **k: ({"documents": [{"docPath": "custom-docs/note.md"}]}, None),
    )
    called = []
    monkeypatch.setattr(server, "add_documents_to_workspace", lambda s, d: called.append(d) or ("x", None))
    text, err = server.upload_local_document(str(f), add_to_workspace=False)
    assert err is None and "custom-docs/note.md" in text
    assert called == []
