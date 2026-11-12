# -*- coding: utf-8 -*-
"""MCP Client 桥接层。

从当前项目（workspace）目录读取 .mcp.json，连接外部 MCP Server
（Streamable HTTP 协议），发现并注册其工具，并在被调用时转发。

连接复用：每个 Server 在一个后台 asyncio 事件循环线程里保持长连接，
同步环境（工具 run）通过 run_coroutine_threadsafe 提交异步调用。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time as _time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import anyio

# 部分 stdio server 在 stdout 打非 JSON 启动日志，mcp 内部 reader 会以
# logger.exception 打一条解析 traceback；会话消息已在下方泵里过滤，这里把
# 该内部 logger 压到 CRITICAL，避免已知噪音刷屏（真实连接失败仍由本层捕获）。
logging.getLogger("mcp.client.stdio").setLevel(logging.CRITICAL)

_DEVNULL = None


def _devnull():
    """stdio 子进程的 stderr 目标：TUI 模式下 sys.stderr 不可用，改用空设备。"""
    global _DEVNULL
    if _DEVNULL is None:
        try:
            _DEVNULL = open(os.devnull, "w", encoding="utf-8")
        except OSError:
            return None
    return _DEVNULL


class MCPBridge:
    """连接、注册、调用 MCP Server 工具的桥。"""

    def __init__(self, workspace: str, connect_timeout: float = 30.0,
                 call_timeout: float = 120.0) -> None:
        self._config: Dict[str, dict] = self._load(Path(workspace or "."))
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._ready_event = threading.Event()             # 注册完成信号
        self._sessions: Dict[str, Any] = {}   # server -> ClientSession
        self._tool_map: Dict[str, Tuple[str, str]] = {}   # 暴露名 -> (server, 原工具名)
        self._tool_meta: Dict[str, dict] = {}             # 暴露名 -> {description, parameters}
        self._errors: Dict[str, str] = {}                 # server -> 连接错误
        self._pending: set = set()
        self.connect_timeout = float(connect_timeout or 30.0)
        self.call_timeout = float(call_timeout or 120.0)
        self._on_change: Optional[Any] = None
        self._started = False

    # ------------------------------------------------------------------
    # 配置读取：当前项目目录下的 .mcp.json
    # ------------------------------------------------------------------
    @staticmethod
    def _load(workspace: Path) -> Dict[str, dict]:
        p = workspace / ".mcp.json"
        if not p.is_file():
            return {}
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
        servers = data.get("mcpServers", data)
        return servers if isinstance(servers, dict) else {}

    @property
    def available(self) -> bool:
        return bool(self._config)

    @property
    def errors(self) -> Dict[str, str]:
        return dict(self._errors)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def start(self) -> None:
        """启动后台事件循环并连接所有配置的 Server。

        连接与注册在后台异步完成，本方法最多等待注册完成（每 Server 默认 30s），
        不阻塞在长连接上。
        """
        if self._started or not self._config:
            return
        self._started = True
        self._loop = asyncio.new_event_loop()
        self._stop_event = asyncio.Event()
        self._pending = set(self._config.keys())
        threading.Thread(target=self._loop.run_forever, daemon=True).start()
        for name, spec in self._config.items():
            asyncio.run_coroutine_threadsafe(
                self._connect_keepalive(name, spec), self._loop
            )
        # 等待所有 Server 完成注册（或超时，未注册的记入 errors）
        deadline = _time.time() + self.connect_timeout
        while self._pending and _time.time() < deadline:
            _time.sleep(0.05)

    def stop(self) -> None:
        if not self._started or not self._loop:
            return
        try:
            self._loop.call_soon_threadsafe(self._stop_event.set)
        except RuntimeError:
            pass

    def set_on_change(self, callback: Optional[Any]) -> None:
        """注册状态变化回调（某个 Server 连上/失败时触发，用于 TUI 动态刷新）。"""
        self._on_change = callback

    def _notify_change(self) -> None:
        if self._on_change is None:
            return
        try:
            self._on_change()
        except Exception:  # noqa: BLE001 - 回调失败不能影响连接
            pass

    # ------------------------------------------------------------------
    # 工具注册信息
    # ------------------------------------------------------------------
    def tool_schemas(self) -> List[dict]:
        """返回给 LLM 的工具 schema（复用本地 Function Calling 契约）。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": meta["description"],
                    "parameters": meta["parameters"],
                },
            }
            for name, meta in self._tool_meta.items()
        ]

    @property
    def tool_names(self) -> List[str]:
        return list(self._tool_meta.keys())

    def status(self) -> Dict[str, Any]:
        """返回各 MCP Server 的连接状态与已注册工具（供 TUI 边栏展示）。"""
        servers: Dict[str, dict] = {}
        for name in self._config:
            tools = [exposed for exposed, (server, _) in self._tool_map.items() if server == name]
            servers[name] = {
                "connected": name in self._sessions,
                "error": self._errors.get(name, ""),
                "tools": tools,
            }
        return {"servers": servers, "tool_count": len(self._tool_map), "available": self.available}

    # ------------------------------------------------------------------
    # 调用转发
    # ------------------------------------------------------------------
    def call(self, exposed: str, arguments: Dict[str, Any]) -> str:
        if exposed not in self._tool_map:
            return "未知的 MCP 工具：%s" % exposed
        server, original = self._tool_map[exposed]
        session = self._sessions.get(server)
        if session is None:
            return "MCP 服务器 %s 未连接成功：%s" % (server, self._errors.get(server, "未知错误"))
        try:
            result = self._submit(
                session.call_tool(original, self._normalize_args(arguments or {})),
                timeout=self.call_timeout,
            )
        except Exception as exc:  # noqa: BLE001
            return "MCP 调用失败（服务器 %s 工具 %s）：%s" % (server, original, exc)
        return self._format_result(result)

    @staticmethod
    def _normalize_args(args: Dict[str, Any]) -> Dict[str, Any]:
        """把模型常传的中文/宽松取值归一化成 MCP server 接受的枚举格式。

        - gender：男/女 → male/female（仅字符串；数字性别保持原样）。
        - date：纯 YYYY-MM-DD 补成 ISO 的 T12:00，满足需要时间的起卦工具。
        """
        args = dict(args)
        gender = args.get("gender")
        if isinstance(gender, str):
            g = gender.strip()
            if g in ("男", "男士", "男性", "male", "M", "m"):
                args["gender"] = "male"
            elif g in ("女", "女士", "女性", "female", "F", "f"):
                args["gender"] = "female"
        date = args.get("date")
        if isinstance(date, str) and len(date.strip()) == 10:
            args["date"] = date.strip() + "T12:00"
        return args

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------
    def _submit(self, coro: Any, timeout: float) -> Any:
        if self._loop is None:
            raise RuntimeError("MCPBridge 尚未启动")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    async def _connect_keepalive(self, name: str, spec: dict) -> None:
        headers = dict(spec.get("headers") or {})
        url = spec.get("url") or spec.get("http") or spec.get("endpoint")
        try:
            from mcp import ClientSession

            if url:
                from mcp.client.streamable_http import (
                    create_mcp_http_client,
                    streamable_http_client,
                )

                http_client = create_mcp_http_client(headers=headers) if headers else None
                context = (
                    streamable_http_client(url, http_client=http_client)
                    if http_client is not None
                    else streamable_http_client(url)
                )
                async with context as (read_stream, write_stream, _session_id):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        await self._finalize(name, session)
                return

            command = spec.get("command")
            if not command:
                self._errors[name] = "缺少 url 或 command"
                self._pending.discard(name)
                self._notify_change()
                return
            from mcp import StdioServerParameters
            from mcp.client.stdio import stdio_client

            args = spec.get("args") or []
            env = spec.get("env")
            params = StdioServerParameters(
                command=command, args=args, env=env or None
            )
            async with stdio_client(params, errlog=_devnull()) as (raw_read, write_stream):
                # 部分 stdio server 会在 stdout 打一行非 JSON 启动日志（如 Bazi），
                # mcp 内部 reader 解析失败后把异常对象塞回读流；这里串一层过滤，
                # 丢弃解析异常，只转发正常会话消息，避免噪音打断会话。
                clean_writer, clean_read = anyio.create_memory_object_stream(0)

                async def _pump_stdio() -> None:
                    async with clean_writer:
                        async for msg in raw_read:
                            if isinstance(msg, BaseException):
                                continue
                            await clean_writer.send(msg)

                pump = asyncio.create_task(_pump_stdio())
                try:
                    async with ClientSession(clean_read, write_stream) as session:
                        await session.initialize()
                        await self._finalize(name, session)
                finally:
                    pump.cancel()
        except Exception as exc:  # noqa: BLE001
            self._errors[name] = self._describe_error(exc)
            self._pending.discard(name)
            self._notify_change()

    @staticmethod
    def _describe_error(exc: BaseException) -> str:
        """把 ExceptionGroup 展开成可读的错误原因。"""
        group = getattr(exc, "exceptions", None)
        if group:
            return "；".join(MCPBridge._describe_error(e) for e in group)
        text = str(exc).strip()
        resp = getattr(exc, "response", None)
        if resp is not None:
            try:
                body = (resp.text or "").strip()[:200]
            except Exception:  # noqa: BLE001
                body = ""
            if body:
                text = "%s ▸ %s" % (text, body)
        return "%s: %s" % (type(exc).__name__, text) if text else type(exc).__name__

    async def _finalize(self, name: str, session: Any) -> None:
        tools = (await session.list_tools()).tools
        self._register(name, session, tools)
        self._pending.discard(name)
        await self._stop_event.wait()

    def _register(self, name: str, session: Any, tools: List[Any]) -> None:
        self._sessions[name] = session
        prefix = name if len(self._config) > 1 else ""
        for tool in tools:
            original = getattr(tool, "name", "")
            if not original:
                continue
            exposed = "%s_%s" % (prefix, original) if prefix else original
            self._tool_map[exposed] = (name, original)
            self._tool_meta[exposed] = {
                "description": getattr(tool, "description", None)
                or "MCP 工具 %s（服务器 %s）" % (original, name),
                "parameters": getattr(tool, "inputSchema", None)
                or {"type": "object", "properties": {}},
            }
        self._notify_change()

    @staticmethod
    def _format_result(result: Any) -> str:
        parts: List[str] = []
        for item in getattr(result, "content", None) or []:
            item_type = getattr(item, "type", "")
            if item_type == "text":
                parts.append(getattr(item, "text", "") or "")
            else:
                try:
                    parts.append(str(item))
                except Exception:  # noqa: BLE001
                    parts.append("")
        text = "\n".join(parts).strip()
        structured = getattr(result, "structuredContent", None)
        if structured:
            try:
                dumped = json.dumps(structured, ensure_ascii=False)
                text = "%s%s%s" % (text, "\n" if text else "", dumped)
            except (TypeError, ValueError):
                pass
        if getattr(result, "isError", False):
            return "[MCP 错误] %s" % (text or "未知错误")
        return text or "(无返回内容)"


__all__ = ["MCPBridge"]
