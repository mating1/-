import base64
import json
import mimetypes
import os
import sys
import uuid
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROTOCOL_VERSION = "2026-07-28"
SERVER_INFO = {"name": "anythingllm-mcp-server", "version": "0.3.0"}

BASE_URL = os.environ.get("ANYTHINGLLM_BASE_URL", "http://localhost:3001").rstrip("/")
API_KEY = os.environ.get("ANYTHINGLLM_API_KEY", "").strip()
if not API_KEY:
    sys.exit("缺少环境变量 ANYTHINGLLM_API_KEY，请先设置 AnythingLLM 后台的 API Key 再启动")
FIXED_SLUG = os.environ.get("ANYTHINGLLM_SLUG", "").strip() or None
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8765"))

ALLOWED_UPLOAD_EXT = {".pdf", ".docx", ".doc", ".txt", ".md", ".csv", ".html", ".pptx", ".xlsx"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

TOOLS = [
    {
        "name": "listWorkspaces",
        "title": "列出工作区",
        "description": "列出 AnythingLLM 中全部工作区及其 slug、文档数量，用于选择要问答或挂载文档的工作区。",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "listDocuments",
        "title": "列出已上传文档",
        "description": "列出 AnythingLLM 系统中已上传的文档及其 docPath，供加入工作区向量化时选用。",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "addDocumentsToWorkspace",
        "title": "把文档加入工作区并向量化",
        "description": "把已上传文档的 docPath 列表加入指定工作区，触发向量化入库；slug 为空时使用默认工作区。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "工作区 slug；留空使用默认工作区"},
                "doc_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要加入工作区的文档 docPath 列表",
                },
            },
            "required": ["doc_paths"],
            "additionalProperties": False,
        },
    },
    {
        "name": "uploadLocalDocument",
        "title": "上传本地文档并入库",
        "description": "读取本机指定路径的文档文件，以 multipart/form-data 上传到 AnythingLLM；可选择是否同时加入默认/指定工作区并触发向量化。支持 pdf/docx/doc/txt/md/csv/html/pptx/xlsx，单文件不超过 50MB。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "本机文档的绝对或相对路径"},
                "slug": {"type": "string", "description": "工作区 slug；留空使用默认工作区"},
                "add_to_workspace": {
                    "type": "boolean",
                    "description": "上传成功后是否加入工作区并向量化，默认 true",
                },
            },
            "required": ["file_path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "askWorkspace",
        "title": "AnythingLLM 工作区问答",
        "description": "基于指定工作区中的已向量化文档，检索相关内容并回答用户的问题。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "要向工作区文档提出的问题"},
                "slug": {"type": "string", "description": "工作区 slug；留空使用默认工作区"},
            },
            "required": ["question"],
            "additionalProperties": False,
        },
    },
]
TOOL_NAMES = {t["name"] for t in TOOLS}


def _http_json(method, path, payload=None, timeout=180):
    headers = {"Authorization": "Bearer %s" % API_KEY}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        return None, "AnythingLLM HTTP %s: %s" % (exc.code, detail)
    except Exception as exc:
        return None, "AnythingLLM 调用失败: %s" % exc


def _http_multipart(path, filename, file_bytes, mime, timeout=180):
    """以 multipart/form-data 上传一个文件到 AnythingLLM，返回解析后的 JSON。"""
    boundary = "----xagent-%s" % uuid.uuid4().hex
    crlf = b"\r\n"
    header = (
        'Content-Disposition: form-data; name="file"; filename="%s"' % filename
    ).encode("utf-8")
    body = b"--" + boundary.encode() + crlf
    body += header + crlf
    body += ("Content-Type: %s" % mime).encode("utf-8") + crlf + crlf
    body += file_bytes + crlf
    body += b"--" + boundary.encode() + b"--" + crlf
    headers = {
        "Authorization": "Bearer %s" % API_KEY,
        "Content-Type": "multipart/form-data; boundary=%s" % boundary,
    }
    req = urllib.request.Request(BASE_URL + path, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        return None, "AnythingLLM HTTP %s: %s" % (exc.code, detail)
    except Exception as exc:
        return None, "AnythingLLM 上传失败: %s" % exc


def resolve_slug():
    if FIXED_SLUG:
        return FIXED_SLUG
    data, err = _http_json("GET", "/api/v1/workspaces")
    if err or not data or not data.get("workspaces"):
        return None
    return data["workspaces"][0]["slug"]


WORKSPACE_SLUG = resolve_slug()


def list_workspaces():
    data, err = _http_json("GET", "/api/v1/workspaces")
    if err:
        return None, err
    workspaces = data.get("workspaces") or []
    if not workspaces:
        return "当前没有任何工作区", None
    lines = ["共 %d 个工作区：" % len(workspaces)]
    for ws in workspaces:
        docs = ws.get("documents")
        count = len(docs) if isinstance(docs, list) else "?"
        lines.append("- %s（slug=%s，文档 %s 篇）" % (ws.get("name"), ws.get("slug"), count))
    return "\n".join(lines), None


def list_documents():
    data, err = _http_json("GET", "/api/v1/documents")
    if err:
        return None, err
    docs = data.get("documents") or []
    if not docs:
        return "系统中暂无已上传文档", None
    lines = ["共 %d 篇文档：" % len(docs)]
    for doc in docs:
        lines.append("- %s（docPath=%s）" % (doc.get("title") or doc.get("docPath"), doc.get("docPath")))
    return "\n".join(lines), None


def add_documents_to_workspace(slug, doc_paths):
    target = slug or WORKSPACE_SLUG
    if not target:
        return None, "未解析到 AnythingLLM 工作区，请检查服务与 ANYTHINGLLM_SLUG 配置"
    if not isinstance(doc_paths, list) or not doc_paths:
        return None, "doc_paths 必须是非空数组"
    data, err = _http_json(
        "POST",
        "/api/v1/workspace/%s/update-embeddings" % target,
        {"adds": doc_paths, "removes": []},
    )
    if err:
        return None, err
    return "已把 %d 篇文档加入工作区 %s 并触发向量化" % (len(doc_paths), target), None


def upload_local_document(file_path, slug=None, add_to_workspace=True):
    """读取本机文档，multipart 上传到 AnythingLLM，可选加入工作区向量化。"""
    if not isinstance(file_path, str) or not file_path.strip():
        return None, "file_path 不能为空"
    path = Path(file_path).expanduser()
    if not path.is_file():
        return None, "本地文件不存在或不是文件：%s" % file_path
    ext = path.suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXT:
        return None, "不支持的文件类型 %s，允许：%s" % (ext, ", ".join(sorted(ALLOWED_UPLOAD_EXT)))
    size = path.stat().st_size
    if size == 0:
        return None, "文件为空：%s" % file_path
    if size > MAX_UPLOAD_BYTES:
        return None, "文件超过 50MB（%d 字节）：%s" % (size, file_path)

    file_bytes = path.read_bytes()
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    data, err = _http_multipart("/api/v1/document/upload", path.name, file_bytes, mime)
    if err:
        return None, err
    docs = data.get("documents") or []
    if not docs:
        return None, "上传响应中未返回文档：%s" % json.dumps(data, ensure_ascii=False)[:200]
    doc_path = docs[0].get("docPath")
    if not doc_path:
        return None, "上传响应缺少 docPath"

    summary = "已上传文档：%s（docPath=%s）" % (docs[0].get("title") or path.name, doc_path)
    if add_to_workspace:
        ws_text, ws_err = add_documents_to_workspace(slug, [doc_path])
        if ws_err:
            return None, summary + "；加入工作区失败：%s" % ws_err
        summary += "；" + ws_text
    return summary, None


def ask_workspace(question, slug=None):
    target = slug or WORKSPACE_SLUG
    if not target:
        return None, "未解析到 AnythingLLM 工作区，请检查服务与 ANYTHINGLLM_SLUG 配置"
    data, err = _http_json(
        "POST",
        "/api/v1/workspace/%s/chat" % target,
        {"message": question, "mode": "query", "sessionId": "mcp"},
    )
    if err:
        return None, err
    if data.get("error"):
        return None, "AnythingLLM: %s" % data["error"]
    return data.get("textResponse") or "", None


def dispatch(name, arguments):
    if name == "listWorkspaces":
        return list_workspaces()
    if name == "listDocuments":
        return list_documents()
    if name == "addDocumentsToWorkspace":
        return add_documents_to_workspace(
            arguments.get("slug") or None, arguments.get("doc_paths")
        )
    if name == "uploadLocalDocument":
        return upload_local_document(
            arguments.get("file_path"),
            arguments.get("slug") or None,
            arguments.get("add_to_workspace", True),
        )
    if name == "askWorkspace":
        return ask_workspace(arguments.get("question"), arguments.get("slug") or None)
    return None, "未知工具: %s" % name


def decode_header_value(value):
    if value.startswith("=?base64?") and value.endswith("?="):
        try:
            return base64.b64decode(value[len("=?base64?"):-2]).decode("utf-8")
        except Exception:
            return None
    return value


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s\n" % (fmt % args))

    def _send(self, code, obj=None):
        body = b""
        if obj is not None:
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _error(self, code, rpc_id, err_code, message, data=None):
        err = {"code": err_code, "message": message}
        if data is not None:
            err["data"] = data
        body = {"jsonrpc": "2.0", "error": err}
        if rpc_id is not None:
            body["id"] = rpc_id
        self._send(code, body)

    def _result(self, rpc_id, result):
        result["_meta"] = {"io.modelcontextprotocol/serverInfo": SERVER_INFO}
        self._send(200, {"jsonrpc": "2.0", "id": rpc_id, "result": result})

    def do_GET(self):
        self._send(405)

    do_DELETE = do_GET

    def _validate(self, msg):
        rpc_id = msg.get("id")
        params = msg.get("params") or {}
        meta = params.get("_meta") or {}
        version_hdr = self.headers.get("MCP-Protocol-Version")
        if not version_hdr:
            return {"code": -32020, "message": "Missing required MCP-Protocol-Version header", "rpc_id": rpc_id}
        if version_hdr != PROTOCOL_VERSION:
            return {
                "code": -32022,
                "message": "Unsupported protocol version: %s" % version_hdr,
                "data": {"supported": [PROTOCOL_VERSION]},
                "rpc_id": rpc_id,
            }
        if meta.get("io.modelcontextprotocol/protocolVersion") != PROTOCOL_VERSION:
            return {"code": -32020, "message": "MCP-Protocol-Version header does not match _meta", "rpc_id": rpc_id}
        if "io.modelcontextprotocol/clientCapabilities" not in meta:
            return {
                "code": -32602,
                "message": "Missing required _meta field: io.modelcontextprotocol/clientCapabilities",
                "rpc_id": rpc_id,
            }
        if self.headers.get("Mcp-Method") != msg.get("method"):
            return {"code": -32020, "message": "Mcp-Method header does not match body method", "rpc_id": rpc_id}
        if msg.get("method") == "tools/call":
            name = params.get("name")
            mcp_name = decode_header_value(self.headers.get("Mcp-Name", ""))
            if not mcp_name or mcp_name != name:
                return {"code": -32020, "message": "Mcp-Name header does not match body name", "rpc_id": rpc_id}
        return None

    def _handle_list(self, rpc_id, params):
        self._result(rpc_id, {"resultType": "complete", "tools": TOOLS})

    def _handle_initialize(self, rpc_id, params):
        self._result(
            rpc_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        )

    def _handle_call(self, rpc_id, params):
        name = params.get("name")
        if name not in TOOL_NAMES:
            self._error(400, rpc_id, -32602, "Unknown tool: %s" % name)
            return
        arguments = params.get("arguments") or {}
        if name in ("askWorkspace",) and not isinstance(arguments.get("question"), str):
            self._error(400, rpc_id, -32602, "Missing required argument: question")
            return
        if name == "addDocumentsToWorkspace" and not isinstance(arguments.get("doc_paths"), list):
            self._error(400, rpc_id, -32602, "Missing required argument: doc_paths")
            return
        if name == "uploadLocalDocument" and not isinstance(arguments.get("file_path"), str):
            self._error(400, rpc_id, -32602, "Missing required argument: file_path")
            return

        text, err = dispatch(name, arguments)
        self._result(
            rpc_id,
            {
                "resultType": "complete",
                "content": [{"type": "text", "text": err if err is not None else text}],
                "isError": err is not None,
            },
        )

    def do_POST(self):
        origin = self.headers.get("Origin")
        if origin:
            host = origin.split("://", 1)[-1].split("/", 1)[0]
            host = host.lstrip("[")
            if host.split(":", 1)[0] not in ("localhost", "127.0.0.1", "::1"):
                self._error(403, None, -32600, "Forbidden: invalid Origin header")
                return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 1024 * 1024:
                self._error(400, None, -32600, "Invalid request body size")
                return
            msg = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(msg, dict):
                raise ValueError()
        except Exception:
            self._error(400, None, -32700, "Parse error")
            return
        rpc_id = msg.get("id")
        if rpc_id is None:
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        try:
            invalid = self._validate(msg)
            if invalid:
                self._error(
                    400,
                    invalid["rpc_id"],
                    invalid["code"],
                    invalid["message"],
                    invalid.get("data"),
                )
                return
            method = msg.get("method")
            if method == "initialize":
                self._handle_initialize(rpc_id, msg.get("params") or {})
            elif method == "notifications/initialized":
                self.send_response(202)
                self.send_header("Content-Length", "0")
                self.end_headers()
            elif method == "tools/list":
                self._handle_list(rpc_id, msg.get("params") or {})
            elif method == "tools/call":
                self._handle_call(rpc_id, msg.get("params") or {})
            else:
                self._error(404, rpc_id, -32601, "Method not found: %s" % method)
        except Exception as exc:
            self._error(500, rpc_id, -32603, "Internal error: %s" % exc)


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    print("MCP server listening on http://%s:%s/mcp" % (HOST, PORT), flush=True)
    if WORKSPACE_SLUG:
        print("Using AnythingLLM workspace: %s" % WORKSPACE_SLUG, flush=True)
    else:
        print("WARNING: could not resolve AnythingLLM workspace", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
