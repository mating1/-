# -*- coding: utf-8 -*-
"""把同步迭代器桥接成异步迭代器。

core 的主流程基于同步的 ``requests`` 实现；为了支持 Textual / FastAPI 等
异步前端，这里把同步生成器安全地搬运到工作线程中，再以异步迭代器的
形式提供给调用方，避免阻塞事件循环。
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Callable, Iterator, TypeVar

T = TypeVar("T")

_SENTINEL = object()


async def iterate_in_thread(factory: Callable[[], Iterator[T]]) -> AsyncIterator[T]:
    """在后台线程中消费同步迭代器，并以异步迭代器的形式产出元素。

    :param factory: 返回同步迭代器的工厂函数（调用时才真正开始工作）。
    """
    loop = asyncio.get_running_loop()
    queue: "asyncio.Queue[Any]" = asyncio.Queue()

    def _worker() -> None:
        try:
            for item in factory():
                loop.call_soon_threadsafe(queue.put_nowait, item)
        except BaseException as exc:  # noqa: BLE001 - 异常需要跨线程回传
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

    task = loop.run_in_executor(None, _worker)
    try:
        while True:
            item = await queue.get()
            if item is _SENTINEL:
                break
            if isinstance(item, BaseException):
                raise item
            yield item
    finally:
        if not task.done():
            task.cancel()
