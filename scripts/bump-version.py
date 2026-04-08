#!/usr/bin/env python3
"""
Auto-versioning script for tracecast packages.
Reads current version, bumps it based on the specified type,
and updates both Python and TypeScript package files.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PYPROJECT = ROOT / "packages" / "tracecast-py" / "pyproject.toml"
PACKAGE_JSON = ROOT / "packages" / "tracecast-ts" / "package.json"


def get_current_version():
    """Get current version from pyproject.toml."""
    content = PYPROJECT.read_text()
    match = re.search(r'version\s*=\s*"(\d+\.\d+\.\d+)"', content)
    if not match:
        raise ValueError("Could not find version in pyproject.toml")
    return match.group(1)


def bump_version(version: str, bump_type: str) -> str:
    """Bump version according to semantic versioning."""
    major, minor, patch = map(int, version.split("."))

    if bump_type == "patch":
        patch += 1
    elif bump_type == "minor":
        minor += 1
        patch = 0
    elif bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    else:
        raise ValueError(f"Invalid bump type: {bump_type}. Use 'major', 'minor', or 'patch'.")

    return f"{major}.{minor}.{patch}"


def update_pyproject(new_version: str):
    """Update version in pyproject.toml."""
    content = PYPROJECT.read_text()
    new_content = re.sub(
        r'(version\s*=\s*)"\d+\.\d+\.\d+"',
        f'\\g<1>"{new_version}"',
        content,
    )
    PYPROJECT.write_text(new_content)
    print(f"✅ Updated pyproject.toml to v{new_version}")


def update_package_json(new_version: str):
    """Update version in package.json."""
    with open(PACKAGE_JSON, "r") as f:
        data = json.load(f)

    data["version"] = new_version

    with open(PACKAGE_JSON, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    print(f"✅ Updated package.json to v{new_version}")


def main():
    parser = argparse.ArgumentParser(description="Bump version for tracecast packages")
    parser.add_argument(
        "bump_type",
        nargs="?",
        default="patch",
        choices=["patch", "minor", "major"],
        help="Type of version bump (default: patch)",
    )
    parser.add_argument(
        "--output-file",
        help="Write new version to a file (for CI/CD)",
    )
    args = parser.parse_args()

    current_version = get_current_version()
    new_version = bump_version(current_version, args.bump_type)

    print(f"📦 Current version: v{current_version}")
    print(f"🚀 New version: v{new_version}")

    update_pyproject(new_version)
    update_package_json(new_version)

    if args.output_file:
        Path(args.output_file).write_text(new_version)
        print(f"📝 Version written to {args.output_file}")

    print("\n✨ Version bump complete!")


if __name__ == "__main__":
    main()
