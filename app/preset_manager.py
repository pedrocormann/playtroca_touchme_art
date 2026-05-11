"""Named presets for the playback-behavior globals (fades, lockout, max duration).

Master volume is intentionally NOT part of a preset — the Pi keeps audio at
maximum and the artist never tunes it through this layer.

Presets are JSON files under app/presets/, named like config_1.json. They are
versioned alongside the code so the same library follows the project from the
Mac playground to the Pi."""
from __future__ import annotations
import json
import re
from pathlib import Path
from threading import Lock

# Only these keys travel with a preset. Master volume is excluded on purpose.
PRESET_KEYS = (
    "retrigger_cooldown_seconds",
    "release_fade_ms",
    "max_play_seconds",
)

VALID_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")
AUTO_NAME_RE = re.compile(r"^config_(\d+)$")


class PresetManager:
    def __init__(self, presets_dir: str | Path):
        self.dir = Path(presets_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    # ── discovery ──────────────────────────────────────────────────────────
    def list(self) -> list[dict]:
        out = []
        for p in sorted(self.dir.glob("*.json")):
            try:
                data = json.loads(p.read_text())
            except Exception:
                continue
            out.append({
                "name": p.stem,
                "values": {k: data.get(k) for k in PRESET_KEYS},
                "saved_at": p.stat().st_mtime,
            })
        return out

    def exists(self, name: str) -> bool:
        return (self.dir / f"{name}.json").exists()

    def get(self, name: str) -> dict | None:
        path = self.dir / f"{name}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except Exception:
            return None

    # ── writes ─────────────────────────────────────────────────────────────
    def _next_auto_name(self) -> str:
        existing = self.list()
        used = set()
        for entry in existing:
            m = AUTO_NAME_RE.match(entry["name"])
            if m:
                used.add(int(m.group(1)))
        n = 1
        while n in used:
            n += 1
        return f"config_{n}"

    def save(self, values: dict, name: str | None = None) -> dict:
        """Persist a preset. If name is empty/None we auto-pick the next
        config_N slot. Returns the saved entry."""
        with self._lock:
            if name:
                name = name.strip()
                if not VALID_NAME_RE.match(name):
                    raise ValueError(f"invalid preset name: {name!r}")
            else:
                name = self._next_auto_name()
            payload = {k: values.get(k) for k in PRESET_KEYS if k in values}
            path = self.dir / f"{name}.json"
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
            tmp.replace(path)
            return {
                "name": name,
                "values": payload,
                "saved_at": path.stat().st_mtime,
            }

    def delete(self, name: str) -> bool:
        with self._lock:
            path = self.dir / f"{name}.json"
            if path.exists():
                path.unlink()
                return True
            return False
