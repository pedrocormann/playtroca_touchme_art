"""JSON-backed config with thread-safe read/write.

Each pad maps to a *group* (a directory of WAV samples). When the pad is
triggered, the sampler picks a random sample from the group. The most recent
choice is exposed via the API so the UI can show "tocando agora".
"""
from __future__ import annotations
import json
import threading
import time
from pathlib import Path
from typing import Any


DEFAULT_NOTES = list(range(48, 72))  # C3..B4 — covers both TouchMe firmware ranges
                                     # (C3 octave for default Drums mode, C4 for Chromatic)

GLOBAL_DEFAULTS = {
    "master_volume": 1.0,
    # ignore re-triggers of the same sample for this many seconds
    "retrigger_cooldown_seconds": 2.0,
    # release fade-out duration in ms
    "release_fade_ms": 5000,
    # hard cap on a single playback, even if the pad keeps being held
    "max_play_seconds": 20.0,
}

PAD_DEFAULTS = {"group": None, "volume": 1.0, "hold": True}


def default_config() -> dict[str, Any]:
    return {
        **GLOBAL_DEFAULTS,
        "pads": {str(n): dict(PAD_DEFAULTS) for n in DEFAULT_NOTES},
    }


class Config:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        # transient (not persisted) — last sample picked per pad, for the UI
        self._last_play: dict[int, dict] = {}
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._data = default_config()
            self._write_unlocked()
        else:
            with self.path.open() as f:
                self._data = json.load(f)
        self._migrate_and_fill()

    def _migrate_and_fill(self):
        for k, v in GLOBAL_DEFAULTS.items():
            self._data.setdefault(k, v)
        pads = self._data.setdefault("pads", {})
        # Track whether this migration is *adding* new pads to an already-mapped
        # config — that means the pad range expanded since last run and we need
        # to redistribute groups across the new pads too.
        had_pads = bool(pads)
        had_mapping = any(p.get("group") for p in pads.values())
        added_new = False
        for n in DEFAULT_NOTES:
            if str(n) not in pads:
                pads[str(n)] = dict(PAD_DEFAULTS)
                if had_pads:
                    added_new = True
            pad = pads[str(n)]
            # drop legacy fields from prior schemas
            pad.pop("loop", None)
            pad.pop("file", None)
            for k, v in PAD_DEFAULTS.items():
                pad.setdefault(k, v)
        # Signal to main.py that we should reshuffle to cover the new range
        self._range_expanded = bool(added_new and had_mapping)
        self._write_unlocked()

    @property
    def range_expanded(self) -> bool:
        return getattr(self, "_range_expanded", False)

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

    # auto-assignment of groups to pads
    def has_any_mapping(self) -> bool:
        with self._lock:
            return any(p.get("group") for p in self._data.get("pads", {}).values())

    def auto_assign_groups(self, groups: list[str], force: bool = False,
                           respect_order: bool = True):
        """Map groups to pads. If respect_order is True (default), groups are
        assumed to come in dark→bright order and are stretched across the pads
        so low MIDI notes get dark groups and high notes get bright ones. If
        False, groups are shuffled randomly and round-robined.

        By default this is a no-op when any pad already has a manual mapping;
        pass force=True to overwrite.
        """
        if not groups:
            return
        with self._lock:
            existing = any(p.get("group") for p in self._data["pads"].values())
            if existing and not force:
                return
            notes = sorted(int(n) for n in self._data["pads"].keys())
            n_pads = len(notes)
            n_groups = len(groups)
            if respect_order and n_groups > 1:
                # Stretch groups across pads, preserving dark→bright ordering.
                # Each pad i gets groups[round(i * (n_groups-1) / (n_pads-1))].
                mapping = []
                for i in range(n_pads):
                    idx = round(i * (n_groups - 1) / max(1, n_pads - 1))
                    mapping.append(groups[idx])
            else:
                import random as _r
                shuffled = list(groups)
                _r.shuffle(shuffled)
                mapping = [shuffled[i % n_groups] for i in range(n_pads)]
            for i, n in enumerate(notes):
                self._data["pads"][str(n)]["group"] = mapping[i]
            self._write_unlocked()

    # last-play (transient)
    def set_last_play(self, note: int, sample: str, group: str | None):
        with self._lock:
            self._last_play[int(note)] = {
                "sample": sample,
                "group": group,
                "at": time.time(),
            }

    def get_last_play(self, note: int) -> dict | None:
        with self._lock:
            return dict(self._last_play[note]) if note in self._last_play else None

    def all_last_plays(self) -> dict[int, dict]:
        with self._lock:
            return {n: dict(v) for n, v in self._last_play.items()}
