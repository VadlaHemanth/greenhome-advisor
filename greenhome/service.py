"""Bounded off-event-loop work, without coupling request state to one replica."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
import threading
from typing import Callable

from greenhome.security import ServiceBusy


def integer_setting(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        raise RuntimeError(f"{name} must be an integer.") from None
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} is outside its supported range.")
    return value


class CalculationService:
    """Bound running + waiting jobs; cancellation never frees active work early.

    Each replica owns its CPU pool. Durable workspace/quota data live outside
    this pool. No unbounded background queue, process-wide monkeypatch or cached
    customer results are used.
    """
    def __init__(self, workers: int = 4, capacity: int = 128):
        if workers < 1 or capacity < workers:
            raise ValueError("Capacity must be at least the positive worker count.")
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="home-calc")
        self.capacity = capacity
        self.pending = 0
        self.lock = threading.Lock()
        self.closed = False

    async def run(self, function: Callable, *args, timeout: float = 25, **kwargs):
        with self.lock:
            if self.closed or self.pending >= self.capacity:
                raise ServiceBusy()
            self.pending += 1
        try:
            future = self.executor.submit(function, *args, **kwargs)
        except Exception:
            with self.lock:
                self.pending -= 1
            raise ServiceBusy() from None

        def completed(_):
            with self.lock:
                self.pending -= 1

        future.add_done_callback(completed)
        wrapped = asyncio.wrap_future(future)
        # Retrieve any late failure without exposing payloads in event-loop logs.
        wrapped.add_done_callback(lambda f: None if f.cancelled() else f.exception())
        try:
            return await asyncio.wait_for(asyncio.shield(wrapped), timeout)
        except asyncio.TimeoutError:
            future.cancel()  # succeeds only for work that has not started
            raise ServiceBusy() from None
        except asyncio.CancelledError:
            future.cancel()
            raise

    def close(self):
        with self.lock:
            self.closed = True
        self.executor.shutdown(wait=False, cancel_futures=True)
