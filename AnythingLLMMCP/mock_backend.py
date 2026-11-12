# -*- coding: utf-8 -*-
"""本地联调用 AnythingLLM 契约桩后端（标准库，零依赖）。

仅用于在本机无真实 AnythingLLM 实例时，验证 B MCP Server 与 C 网页到后端的
HTTP 契约、Bearer 鉴权、请求体与 SSE 解析；不做真实向量入库与语义检索。
启动：python mock_backend.py  监听 127.0.0.1:3001。
"""
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = os.environ.get("MOCK_HOST", "127.0.0.1")
PORT = int(os.environ.get("MOCK_PORT", "3001"))
EXPECTED_KEY = os.environ.get("ANYTHINGLLM_API_KEY", "").strip()

WORKSPACES = [
    {
        "name": "演示工作区",
        "slug": "demo-workspace",
        "documents": [{"docPath": "custom-说明文档.txt", "title": "说明文档.txt"}],
    }
]
DOCUMENTS = [{"docPath": "custom-说明文档.txt", "title": "说明文档.txt"}]


def _parse_upload_filename(body, content_type):
    match = re.search(r'boundary=("?)([^";]+)\1', content_type or "")
    if not match:
        return "upload.bin"
    boundary = match.group(2).encode("utf-8")
    for part in body.split(b"--" + boundary):
        if b"Content-Disposition" in part and b"filename=" in part:
            fm = re.search(rb'filename="([^"]+)"', part)
            if fm:
                return fm.group(1).decode("utf-8", "replace")
    return "upload.bin"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("[mock-anythingllm] %s\n" % (fmt % args))

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _authed(self):
        if not EXPECTED_KEY:
            return True
        auth = self.headers.get("Authorization", "")
        return auth == "Bearer %s" % EXPECTED_KEY

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if not self._authed():
            self._send_json(401, {"error": "invalid api key"})
            return
        if self.path.rstrip("/") == "/api/v1/workspaces":
            self._send_json(200, {"workspaces": WORKSPACES})
        elif self.path.rstrip("/") == "/api/v1/documents":
            self._send_json(200, {"documents": DOCUMENTS})
        else:
            self._send_json(404, {"error": "not found: %s" % self.path})

    def do_POST(self):
        if not self._authed():
            self._send_json(401, {"error": "invalid api key"})
            return

        ws_chat = re.match(r"^/api/v1/workspace/([^/]+)/chat/?$", self.path)
        ws_stream = re.match(r"^/api/v1/workspace/([^/]+)/stream-chat/?$", self.path)
        ws_embed = re.match(r"^/api/v1/workspace/([^/]+)/update-embeddings/?$", self.path)

        if self.path.rstrip("/") == "/api/v1/document/upload":
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length)
            filename = _parse_upload_filename(body, self.headers.get("Content-Type", ""))
            self._send_json(200, {"documents": [{"docPath": "custom-" + filename, "title": filename}]})
            return

        if ws_embed:
            self._read_json()
            self._send_json(200, {"success": True, "added": True})
            return

        payload = self._read_json()
        message = payload.get("message") or payload.get("question") or ""

        if ws_stream:
            self._sse(ws_stream.group(1), message)
            return
        if ws_chat:
            self._send_json(200, {"textResponse": "（桩后端）已收到：%s" % message})
            return

        self._send_json(404, {"error": "not found: %s" % self.path})

    def _sse(self, slug, message):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self._cors()
        self.end_headers()
        chunks = ["（桩后端）", "已收到你的问题：", message]
        for chunk in chunks:
            payload = json.dumps({"textResponse": chunk}, ensure_ascii=False)
            self.wfile.write(("data: %s\n\n" % payload).encode("utf-8"))
            self.wfile.flush()
        self.wfile.write(
            ("data: %s\n\n" % json.dumps({"closed": True}, ensure_ascii=False)).encode("utf-8")
        )
        self.wfile.flush()
        self.close_connection = True


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    print("mock AnythingLLM backend listening on http://%s:%s" % (HOST, PORT), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
