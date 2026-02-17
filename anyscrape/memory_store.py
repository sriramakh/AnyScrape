from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, Optional
from urllib.parse import urlparse


def _default_memory_path() -> str:
    """
    Default on-disk location for AnyScrape memory.

    Stored next to the package so it persists across runs but
    stays local to this project.
    """
    base_dir = os.path.dirname(__file__)
    return os.path.join(base_dir, "memory.json")


def get_domain_from_url(url: str) -> Optional[str]:
    """
    Extract hostname from a URL, or None if parsing fails.
    """
    try:
        parsed = urlparse(url)
        return parsed.netloc or None
    except Exception:
        return None


class MemoryStore:
    """
    Simple JSON-backed memory store shared across agents.

    Currently tracks per-agent, per-domain statistics and preferences
    so that future runs can adapt based on past experience.
    """

    def __init__(self, path: str | None = None) -> None:
        self._path = path or _default_memory_path()
        self._lock = threading.Lock()
        # _data structure:
        # {
        #   "decision_agent": { "<domain>": {...} },
        #   "crawl_agent": { "<domain>": {...} }
        # }
        self._data: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    if isinstance(raw, dict):
                        self._data = raw  # type: ignore[assignment]
        except Exception:
            # On any error, fall back to empty memory rather than failing the app.
            self._data = {}

    def _save(self) -> None:
        directory = os.path.dirname(self._path)
        os.makedirs(directory, exist_ok=True)
        tmp_path = self._path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, sort_keys=True)
        os.replace(tmp_path, self._path)

    def _agent_bucket(self, agent_name: str) -> Dict[str, Dict[str, Any]]:
        return self._data.setdefault(agent_name, {})

    def get_domain_stats(self, agent_name: str, domain: str) -> Dict[str, Any]:
        """
        Return mutable stats dict for a given agent+domain.
        """
        bucket = self._agent_bucket(agent_name)
        return bucket.setdefault(domain, {})

    def increment(self, agent_name: str, domain: str, key: str, delta: int = 1) -> None:
        with self._lock:
            stats = self.get_domain_stats(agent_name, domain)
            stats[key] = int(stats.get(key, 0)) + delta
            self._save()

    def set_value(self, agent_name: str, domain: str, key: str, value: Any) -> None:
        with self._lock:
            stats = self.get_domain_stats(agent_name, domain)
            stats[key] = value
            self._save()

    def get_value(
        self, agent_name: str, domain: str, key: str, default: Any | None = None
    ) -> Any:
        stats = self._agent_bucket(agent_name).get(domain, {})
        return stats.get(key, default)


_memory_store: Optional[MemoryStore] = None


def get_memory_store() -> MemoryStore:
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore()
    return _memory_store


