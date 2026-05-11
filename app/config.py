"""JSON-backed config with thread-safe read/write."""
from __future__ import annotations
import json
import threading
from pathlib import Path
from typing import Any


DEFAULT_NOTES = list(range(60, 72))  # C4..B4 — TouchMe Playtronica default range

GLOBAL_DEFAULTS = {
    "master_volume": 1.0,
    # ignore re-triggers of the same sample for this many seconds (prevents
    # "remix at every touch" when visitors tap repeatedly)
    "retrigger_cooldown_seconds": 2.0,
    # when a pad is released (or max time hits), fade audio out over this many ms
    "release_fade_ms": 5000,
    # hard cap on how long one playback can last, even if the visitor keeps holding
    "max_play_seconds": 20.0,
}

PAD_DEFAULTS = {"file": None, "volume": 1.0, "hold": True}


def default_config() -> dict[str, Any]:
    return {
        **GLOBAL_DEFAULTS,
        "pads": {str(n): dict(PAD_DEFAULTS) for n in DEFAULT_NOTES},
    }


class Config:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._data = default_config()
            self._write_unlocked()
        else:
            with self.path.open() as f:
                self._data = json.load(f)
        self._migrate_and_fill()

    def _migrate_and_fill(self):
        # Ensure all global keys exist
        for k, v in GLOBAL_DEFAULTS.items():
            self._data.setdefault(k, v)
        # Ensure each pad has all fields. We drop the legacy "loop" flag — the new
        # behavior is "hold" (default True) which models the artist's spec: while
        # the visitor touches, audio plays; on release, fade out.
        pads = self._data.setdefault("pads", {})
        for n in DEFAULT_NOTES:
            pad = pads.setdefault(str(n), dict(PAD_DEFAULTS))
            pad.pop("loop", None)
            for k, v in PAD_DEFAULTS.items():
                pad.setdefault(k, v)
        self._write_unlocked()

    def _write_unlocked(self):
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
        tmp.replace(self.path)

    def snapshot(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self._data))

    def pad(self, note: int) -> dict:
        with self._lock:
            return dict(self._data["pads"].get(str(note), dict(PAD_DEFAULTS)))

    def update_pad(self, note: int, patch: dict):
        with self._lock:
            pad = self._data["pads"].setdefault(str(note), dict(PAD_DEFAULTS))
            for k in PAD_DEFAULTS:
                if k in patch:
                    pad[k] = patch[k]
            self._write_unlocked()

    def get_global(self, key: str, default=None):
        with self._lock:
            return self._data.get(key, default)

    def set_global(self, key: str, value):
        if key not in GLOBAL_DEFAULTS:
            raise KeyError(f"Unknown global key: {key}")
        with self._lock:
            self._data[key] = value
            self._write_unlocked()

    @property
    def master_volume(self) -> float:
        with self._lock:
            return float(self._data.get("master_volume", 1.0))
