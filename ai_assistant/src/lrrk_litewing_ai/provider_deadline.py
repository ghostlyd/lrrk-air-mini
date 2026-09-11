"""Cooperative deadline/cancellation for asynchronous provider operations."""
import asyncio
import math


async def run_bounded(operation, *, timeout_s, stop=lambda: False):
    """Run once; never retry. Operations must honor asyncio cancellation.

    This is not a process kill switch for blocking or cancellation-suppressing
    callbacks. Cancellation does not prove that remote billing was cancelled.
    """
    if (isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float))
            or not math.isfinite(timeout_s) or not 0 < timeout_s <= 60
            or not callable(operation) or not callable(stop)):
        raise ValueError('invalid provider deadline')
    if stop():
        raise asyncio.CancelledError()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    task = asyncio.create_task(operation())
    try:
        while True:
            if stop():
                raise asyncio.CancelledError()
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError('provider deadline expired')
            done, _ = await asyncio.wait({task}, timeout=min(.05, remaining))
            if done:
                if stop():
                    raise asyncio.CancelledError()
                return task.result()
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
