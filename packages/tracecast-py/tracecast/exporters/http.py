"""HTTP exporter — push traces to a TraceCast ingest endpoint.

Designed for fire-and-forget clients: pair with ``background_export=True`` so the
request path only enqueues; this class does the short network hop on the worker.
Uses stdlib ``urllib`` only (no extra deps on bot hosts).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from ..models.trace import Trace
from .base import BaseExporter

_logger = logging.getLogger("tracecast")

DEFAULT_TIMEOUT = 2.0
DEFAULT_BATCH_CHUNK = 50


def _default_timeout() -> float:
    raw = os.environ.get("TRACECAST_HTTP_TIMEOUT")
    if raw is None or raw == "":
        return DEFAULT_TIMEOUT
    try:
        return max(0.1, float(raw))
    except ValueError:
        return DEFAULT_TIMEOUT


def _batch_chunk_size() -> int:
    raw = os.environ.get("TRACECAST_HTTP_BATCH_SIZE")
    if raw is None or raw == "":
        return DEFAULT_BATCH_CHUNK
    try:
        return max(1, min(200, int(raw)))
    except ValueError:
        return DEFAULT_BATCH_CHUNK


def _env_token() -> Optional[str]:
    for key in ("TRACECAST_INGEST_TOKEN", "TRACECAST_HTTP_TOKEN"):
        raw = os.environ.get(key)
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return None


def _env_basic_auth() -> Optional[tuple]:
    raw = os.environ.get("TRACECAST_AUTH")
    if not raw or ":" not in raw:
        return None
    user, _, password = raw.partition(":")
    if not user:
        return None
    return user, password


class HttpExporter(BaseExporter):
    """POST traces to ``{base_url}/api/ingest`` or ``/api/ingest/batch``."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: Optional[float] = None,
        auth: Optional[tuple] = None,
        token: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        path_prefix: str = "",
        batch_chunk: Optional[int] = None,
    ):
        url = (base_url or "").strip().rstrip("/")
        if not url:
            raise ValueError("HttpExporter base_url is required")
        self.base_url = url
        self.timeout = timeout if timeout is not None else _default_timeout()
        self._auth = auth if auth is not None else _env_basic_auth()
        self._token = token if token is not None else _env_token()
        self._headers = dict(headers or {})
        self._batch_chunk = batch_chunk if batch_chunk is not None else _batch_chunk_size()
        if path_prefix:
            self._prefix = path_prefix.rstrip("/")
        else:
            self._prefix = ""

    def _endpoint(self, path: str) -> str:
        if self.base_url.endswith("/tracecast") or (
            self._prefix and self.base_url.rstrip("/").endswith(self._prefix)
        ):
            return f"{self.base_url}{path}"
        if self._prefix:
            return f"{self.base_url}{self._prefix}{path}"
        return f"{self.base_url}{path}"

    def _post(self, path: str, body: Any) -> dict:
        url = self._endpoint(path)
        data = json.dumps(body, default=str).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **self._headers,
        }
        if self._token:
            headers["X-TraceCast-Token"] = self._token
            headers.setdefault("Authorization", f"Bearer {self._token}")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        if self._auth and "Authorization" not in headers:
            import base64

            token = base64.b64encode(
                f"{self._auth[0]}:{self._auth[1]}".encode("utf-8")
            ).decode("ascii")
            req.add_header("Authorization", f"Basic {token}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                if not raw:
                    return {"status": resp.status}
                try:
                    return json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError:
                    return {
                        "status": resp.status,
                        "raw": raw.decode("utf-8", errors="replace"),
                    }
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"HttpExporter HTTP {e.code} {url}: {detail}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"HttpExporter network error {url}: {e.reason}") from e
        except TimeoutError as e:
            raise RuntimeError(
                f"HttpExporter timeout {url} after {self.timeout}s"
            ) from e

    def export(self, trace: Trace) -> None:
        self.export_doc(trace.to_dict())

    def export_doc(self, doc: dict) -> None:
        # Always batch endpoint — one code path, server queues either way.
        result = self._post("/api/ingest/batch", {"traces": [doc]})
        if isinstance(result, dict) and result.get("dropped", 0) > 0:
            raise RuntimeError(f"HttpExporter server dropped trace: {result}")

    def export_docs_batch(self, docs: List[Dict[str, Any]]) -> None:
        if not docs:
            return
        chunk = self._batch_chunk
        for i in range(0, len(docs), chunk):
            part = docs[i : i + chunk]
            result = self._post("/api/ingest/batch", {"traces": part})
            if isinstance(result, dict) and result.get("dropped", 0) > 0:
                raise RuntimeError(
                    f"HttpExporter server dropped {result.get('dropped')} traces: {result}"
                )

    def export_summary(self, summary: dict) -> None:
        # Summaries use same ingest path (same store on server).
        # Priority metric path: tokens/count even when full graph failed.
        self.export_doc(summary)
