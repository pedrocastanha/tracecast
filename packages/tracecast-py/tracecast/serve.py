import os
from typing import Optional

from .exporters.base import BaseExporter


def build_exporter_from_dsn(
    dsn: str,
    *,
    db: Optional[str] = None,
    collection: Optional[str] = None,
    table: Optional[str] = None,
) -> BaseExporter:
    low = dsn.lower()
    if low.startswith(("postgresql://", "postgres://")):
        from .exporters.postgres import PostgresExporter
        return PostgresExporter(dsn, table=table or "traces")
    if low.startswith(("mongodb://", "mongodb+srv://")):
        from .exporters.mongo import MongoExporter
        return MongoExporter(dsn, db=db or "tracecast", collection=collection or "traces")
    if low.startswith("file://"):
        from .exporters.json_file import JsonFileExporter
        return JsonFileExporter(dsn[len("file://"):])
    if low.endswith((".jsonl", ".json")):
        from .exporters.json_file import JsonFileExporter
        return JsonFileExporter(dsn)
    raise ValueError(
        f"Unsupported TRACECAST_STORE dsn: {dsn!r}. "
        "Use postgresql://, mongodb://, file:// or a .jsonl path."
    )


def _parse_auth(value: Optional[str]):
    if not value or ":" not in value:
        return None
    user, _, password = value.partition(":")
    return (user, password)


def serve_from_env() -> None:
    dsn = os.environ.get("TRACECAST_STORE")
    if not dsn:
        raise SystemExit(
            "TRACECAST_STORE is required. Example:\n"
            "  TRACECAST_STORE=mongodb://host:27017 tracecast-server"
        )
    host = os.environ.get("TRACECAST_HOST", "127.0.0.1")
    port = int(os.environ.get("TRACECAST_PORT", "7777"))
    prefix = os.environ.get("TRACECAST_PREFIX", "/tracecast")
    max_traces = int(os.environ.get("TRACECAST_MAX_TRACES", "500"))
    db = os.environ.get("TRACECAST_DB")
    collection = os.environ.get("TRACECAST_COLLECTION")
    table = os.environ.get("TRACECAST_TABLE")
    auth = _parse_auth(os.environ.get("TRACECAST_AUTH"))
    cors = os.environ.get("TRACECAST_CORS")
    cors_origins = [o.strip() for o in cors.split(",")] if cors else None

    exporter = build_exporter_from_dsn(dsn, db=db, collection=collection, table=table)

    from .dashboard.reader import TraceReader
    from .dashboard.standalone import serve_dashboard

    reader = TraceReader([exporter], max_traces=max_traces)
    serve_dashboard(
        reader, host=host, port=port, prefix=prefix,
        auth=auth, cors_origins=cors_origins,
    )


def main() -> None:
    serve_from_env()


if __name__ == "__main__":
    main()
