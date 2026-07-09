from __future__ import annotations

import os
import random
import time
from typing import Callable, Optional, TypeVar

T = TypeVar("T")

DEFAULT_EXPORT_RETRIES = 3
DEFAULT_EXPORT_RETRY_BASE = 0.2


def default_export_retries() -> int:
    raw = os.environ.get("TRACECAST_EXPORT_RETRIES")
    if raw is None or raw == "":
        return DEFAULT_EXPORT_RETRIES
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_EXPORT_RETRIES


def default_export_retry_base() -> float:
    raw = os.environ.get("TRACECAST_EXPORT_RETRY_BASE")
    if raw is None or raw == "":
        return DEFAULT_EXPORT_RETRY_BASE
    try:
        return max(0.0, float(raw))
    except ValueError:
        return DEFAULT_EXPORT_RETRY_BASE


def retry_call(
    fn: Callable[[], T],
    *,
    attempts: Optional[int] = None,
    base_delay: Optional[float] = None,
    on_retry: Optional[Callable[[int, BaseException], None]] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    n = attempts if attempts is not None else default_export_retries()
    base = base_delay if base_delay is not None else default_export_retry_base()
    if n < 1:
        n = 1
    last: Optional[BaseException] = None
    for i in range(n):
        try:
            return fn()
        except BaseException as exc:
            last = exc
            if i + 1 >= n:
                break
            if on_retry is not None:
                on_retry(i + 1, exc)
            if base > 0:
                delay = base * (2 ** i)
                delay = delay * (0.5 + random.random())
                sleep(delay)
    assert last is not None
    raise last
