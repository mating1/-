# Pet Hospital MCP Service

This project exposes the Go pet hospital REST API through a Python MCP 2.0.0 server using the official `mcp` SDK and the 2026-07-28 protocol.

## Requirements

- Python 3.11+
- Go pet-hospital REST API running locally
- `mcp==2.0.0`
- `httpx`
- `pydantic`

## Install

```bash
cd pet_hospital_mcp
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -U pip
pip install -e .[dev]
```

## Environment

The service reads these environment variables:

- `PET_HOSPITAL_BASE_URL` — default `http://127.0.0.1:8080`
- `MCP_HOST` — default `127.0.0.1`
- `MCP_PORT` — default `8000`

## Start the Go API first

The Go pet hospital service must be running before the MCP service starts:

```bash
# in the project that contains the Go API
./pethospital.exe
# or on Unix-like systems
./pethospital
```

Then open the API at `http://127.0.0.1:8080/`.

## Start the MCP service

```bash
cd pet_hospital_mcp
python -m pet_hospital_mcp
```

The server exposes the Streamable HTTP endpoint at:

- `http://127.0.0.1:8000/mcp`
- health check: `http://127.0.0.1:8000/health`

## SDK and protocol

- Python SDK: `mcp==2.0.0`
- Protocol version: `2026-07-28`
- Server class: `MCPServer`
- Transport: stateless Streamable HTTP

## Tool

### list_pets

This tool wraps `GET /api/v1/pets`.

Example input:

```json
{
  "species": "犬",
  "status": "待就诊",
  "sortBy": "totalCost",
  "order": "desc",
  "page": 1,
  "pageSize": 10
}
```

Example call:

```json
{
  "name": "list_pets",
  "arguments": {
    "species": "犬",
    "status": "待就诊",
    "sortBy": "totalCost",
    "order": "desc",
    "page": 1,
    "pageSize": 10
  }
}
```

## Validate with MCP Inspector or SDK client

```bash
npx @modelcontextprotocol/inspector
```

Then connect to `http://127.0.0.1:8000/mcp` and verify that the server advertises the `list_pets` tool and can call it successfully.

## Logging

Every `list_pets` call emits one structured JSON line to stderr:

```json
{"timestamp": "...", "level": "INFO", "logger": "pet_hospital_mcp.tools.list_pets",
 "message": "tool call list_pets", "tool_name": "list_pets",
 "params": {...}, "status": "ok", "duration_ms": 12.34}
```

`status` takes one of `ok` / `validation_error` / `backend_timeout` /
`backend_unavailable` / `backend_api_error` / `backend_invalid_response`.

Fields `ownerPhone`, `ownerAddr`, `chipNo` and their snake_case forms
(`owner_phone`, `owner_addr`, `chip_no`) are replaced with `[REDACTED]`
recursively at any nesting depth, before the record is serialized.

## Testing

```bash
cd pet_hospital_mcp
pytest -q
```

Expected result: `13 passed` — 7 个用例函数，其中一个通过参数化展开为 7 组，合计 13 项。All tests use
`httpx.MockTransport` and never touch the real Go service.
