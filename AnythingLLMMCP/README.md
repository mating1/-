# anythingllm-mcp-server

基于 MCP 2026-07-28（Streamable HTTP）协议、连接本地 AnythingLLM 的极简 MCP Server。把工作区管理、文档列表、本地文档上传、向量化挂载与文档检索问答暴露为 5 个工具。

## 需求

- Python 3.9+（仅标准库，零依赖）

## 运行

```bash
python server.py
```

默认监听 `http://127.0.0.1:8765/mcp`。

## 配置（环境变量）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ANYTHINGLLM_BASE_URL` | `http://localhost:3001` | AnythingLLM 地址 |
| `ANYTHINGLLM_API_KEY` | 无（必填） | AnythingLLM API Key；未设置时启动直接报错退出 |
| `ANYTHINGLLM_SLUG` | 空 | 默认工作区 slug；为空时启动时自动探测第一个工作区 |
| `HOST` | `127.0.0.1` | 监听地址 |
| `PORT` | `8765` | 监听端口 |

示例：

```bash
set ANYTHINGLLM_API_KEY=your-key
set PORT=9000
python server.py
```

## 提供的工具

| 工具 | 说明 | 主要参数 |
| --- | --- | --- |
| `listWorkspaces` | 列出全部工作区及其 slug、文档数量 | 无 |
| `listDocuments` | 列出系统中已上传文档及 docPath | 无 |
| `uploadLocalDocument` | 读取本机文件，multipart/form-data 上传到 AnythingLLM，可选加入工作区向量化；扩展名白名单、50MB 上限 | `file_path`（必填）、`slug`（可选）、`add_to_workspace`（可选，默认 true） |
| `addDocumentsToWorkspace` | 把已上传文档加入指定工作区并触发向量化 | `slug`（可选）、`doc_paths`（数组，必填） |
| `askWorkspace` | 基于工作区已向量化文档检索问答 | `question`（必填）、`slug`（可选） |

## 客户端接入

只要支持 2026-07-28 Streamable HTTP 的 MCP 客户端，配置 URL 为 `http://127.0.0.1:8765/mcp` 即可。客户端先完成 `initialize` 握手，再调用 `tools/list` 与 `tools/call`。

xAgent 侧在工作区 `.mcp.json` 中登记：

```json
"AnythingLLM": {
  "type": "streamable-http",
  "url": "http://127.0.0.1:8765/mcp"
}
```

## 手动测试

`tools/list`：

```bash
curl.exe -X POST http://127.0.0.1:8765/mcp ^
  -H "Content-Type: application/json" ^
  -H "MCP-Protocol-Version: 2026-07-28" ^
  -H "Mcp-Method: tools/list" ^
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{\"_meta\":{\"io.modelcontextprotocol/protocolVersion\":\"2026-07-28\",\"io.modelcontextprotocol/clientCapabilities\":{}}}}"
```

`tools/call`：

```bash
curl.exe -X POST http://127.0.0.1:8765/mcp ^
  -H "Content-Type: application/json" ^
  -H "MCP-Protocol-Version: 2026-07-28" ^
  -H "Mcp-Method: tools/call" ^
  -H "Mcp-Name: askWorkspace" ^
  -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"askWorkspace\",\"arguments\":{\"question\":\"胡芳是谁\"},\"_meta\":{\"io.modelcontextprotocol/protocolVersion\":\"2026-07-28\",\"io.modelcontextprotocol/clientCapabilities\":{}}}}"
```

## 测试

```bash
python -m pytest tests/ -q
```

## 本地联调桩（非真实实例）

本机无真实 AnythingLLM 时，可用 `mock_backend.py` 起一个只实现契约的桩后端（标准库、零依赖），监听 `127.0.0.1:3001`，用于验证 MCP Server 到后端的 HTTP 往返、Bearer 鉴权、multipart 上传与 SSE；**不做真实向量入库与语义检索**。

```bash
set ANYTHINGLLM_API_KEY=sk-mock-anythingllm-local
python mock_backend.py
```

再以同样的 `ANYTHINGLLM_API_KEY`、`ANYTHINGLLM_BASE_URL=http://127.0.0.1:3001`、`ANYTHINGLLM_SLUG=demo-workspace` 启动 `server.py`，即可走真实 HTTP 的 `initialize → tools/list → tools/call` 往返。

## 已知限制

- 上传仅覆盖白名单扩展名（pdf/docx/doc/txt/md/csv/html/pptx/xlsx）与 50MB 上限；`mock_backend.py` 为联调桩，返回固定演示数据，不代表真实 AnythingLLM 的入库与检索结果；接入真实实例后需重新闭环验证。
