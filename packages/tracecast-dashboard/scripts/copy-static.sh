#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DASHBOARD_DIR="$(dirname "$SCRIPT_DIR")"
DIST="$DASHBOARD_DIR/dist"

PY_STATIC="$DASHBOARD_DIR/../tracecast-py/tracecast/dashboard/static"

mkdir -p "$PY_STATIC"
rm -rf "$PY_STATIC"/* 2>/dev/null || true
cp -r "$DIST"/. "$PY_STATIC/"

echo "Copied dashboard build to Python static dir"
