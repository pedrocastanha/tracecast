"""Prompt management client: versioned prompts, label resolution, in-memory
TTL cache, and auto-linking the resolved version to the active trace."""
import time
from typing import Any, Dict, List, Optional

from .models import PromptVersion
from ..core.scoring import _resolve_exporters

# cache: (name, selector) -> (PromptVersion, expires_at_epoch)
_CACHE: Dict[tuple, tuple] = {}


def clear_cache() -> None:
    _CACHE.clear()


def _readable(exporters):
    for exporter in exporters:
        if callable(getattr(exporter, "query_prompts", None)):
            return exporter
    return None


def _writable(exporters) -> List:
    return [e for e in exporters if callable(getattr(e, "export_prompt", None))]


def _all_rows(name: str, exporters) -> List[dict]:
    exporter = _readable(exporters)
    if exporter is None:
        return []
    return exporter.query_prompts(name=name)


def _link_to_trace(pv: PromptVersion, tracer) -> None:
    from ..core.tracer import Tracer
    trace = (tracer.current() if tracer is not None else Tracer.current())
    if trace is not None:
        trace.metadata["prompt_name"] = pv.name
        trace.metadata["prompt_version"] = pv.version


def create_prompt(name: str, template: str, *, labels: Optional[List[str]] = None,
                  config: Optional[Dict[str, Any]] = None, exporters=None, tracer=None) -> PromptVersion:
    exporters = _resolve_exporters(exporters, tracer)
    rows = _all_rows(name, exporters)
    next_version = max((r.get("version", 0) for r in rows), default=0) + 1
    pv = PromptVersion(name=name, version=next_version, template=template,
                       labels=list(labels or []), config=config or {})
    for exporter in _writable(exporters):
        exporter.export_prompt(pv)
    if labels:
        # a label points to at most one version per name
        for label in labels:
            _move_label(name, next_version, label, exporters, rows + [pv.to_dict()])
    _invalidate(name)
    return pv


def set_label(name: str, version: int, label: str, *, exporters=None, tracer=None) -> None:
    exporters = _resolve_exporters(exporters, tracer)
    _move_label(name, version, label, exporters, _all_rows(name, exporters))
    _invalidate(name)


def _move_label(name: str, version: int, label: str, exporters, rows: List[dict]) -> None:
    writers = _writable(exporters)
    seen = set()
    for row in rows:
        if row.get("name") != name:
            continue
        v = row.get("version")
        if v in seen:
            continue
        seen.add(v)
        labels = list(row.get("labels", []))
        changed = False
        if v == version and label not in labels:
            labels.append(label)
            changed = True
        elif v != version and label in labels:
            labels.remove(label)
            changed = True
        if changed:
            pv = PromptVersion.from_dict({**row, "labels": labels})
            for exporter in writers:
                exporter.export_prompt(pv)


def get_prompt(name: str, *, label: Optional[str] = "production", version: Optional[int] = None,
               exporters=None, tracer=None, cache_ttl: float = 60.0) -> PromptVersion:
    exporters = _resolve_exporters(exporters, tracer)
    selector = f"v:{version}" if version is not None else f"l:{label}"
    key = (name, selector)
    cached = _CACHE.get(key)
    now = time.time()
    if cached and cached[1] > now:
        pv = cached[0]
        _link_to_trace(pv, tracer)
        return pv

    rows = _all_rows(name, exporters)
    if not rows:
        if _readable(exporters) is None:
            raise RuntimeError(
                f"no prompt exporter configured; cannot resolve prompt '{name}'"
            )
        raise ValueError(f"prompt not found: {name}")

    rows = [r for r in rows if r.get("name") == name]
    if version is not None:
        match = next((r for r in rows if r.get("version") == version), None)
        if match is None:
            raise ValueError(f"prompt '{name}' has no version {version}")
    elif label is not None:
        match = next((r for r in rows if label in r.get("labels", [])), None)
        if match is None:
            available = sorted({lb for r in rows for lb in r.get("labels", [])})
            raise ValueError(
                f"prompt '{name}' has no version labeled '{label}'. Available labels: {available}"
            )
    else:
        match = max(rows, key=lambda r: r.get("version", 0))

    pv = PromptVersion.from_dict(match)
    if cache_ttl > 0:
        _CACHE[key] = (pv, now + cache_ttl)
    _link_to_trace(pv, tracer)
    return pv


def _invalidate(name: str) -> None:
    for key in [k for k in _CACHE if k[0] == name]:
        _CACHE.pop(key, None)
