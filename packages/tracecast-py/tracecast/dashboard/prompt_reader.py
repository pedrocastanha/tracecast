from typing import List, Optional


class PromptReader:
    def __init__(self, exporters: list):
        self._exporters = exporters

    def _readable(self):
        for exporter in self._exporters:
            if callable(getattr(exporter, "query_prompts", None)):
                return exporter
        return None

    def list_prompts(self) -> List[dict]:
        """One summary per prompt name (latest version + labels)."""
        exporter = self._readable()
        if exporter is None:
            return []
        rows = exporter.query_prompts()
        by_name: dict = {}
        for row in rows:
            name = row.get("name")
            entry = by_name.setdefault(name, {"name": name, "latest_version": 0,
                                              "versions": 0, "labels": []})
            entry["versions"] += 1
            if row.get("version", 0) >= entry["latest_version"]:
                entry["latest_version"] = row.get("version", 0)
            for label in row.get("labels", []):
                if label not in entry["labels"]:
                    entry["labels"].append(label)
        return sorted(by_name.values(), key=lambda e: e["name"])

    def get_versions(self, name: str) -> Optional[List[dict]]:
        exporter = self._readable()
        if exporter is None:
            return None
        rows = [r for r in exporter.query_prompts(name=name) if r.get("name") == name]
        if not rows:
            return None
        return sorted(rows, key=lambda r: r.get("version", 0))
