"""Polyphonic sample player driven by groups of samples.

A "group" is a subdirectory of samples_dir containing one or more .wav files.
When a pad is triggered, a random sample is chosen from the configured group.
Same retrigger lockout, hold-to-play, fade-out and max-play semantics apply.
"""
from __future__ import annotations
import logging
import random
import time
from pathlib import Path
from threading import Lock, Timer

import pygame

log = logging.getLogger(__name__)

NUM_CHANNELS = 16
SAMPLE_RATE = 44100
BUFFER_SIZE = 512  # ~12ms @ 44.1kHz


class Sampler:
    def __init__(self, samples_dir: str | Path, config):
        self.samples_dir = Path(samples_dir)
        self.config = config
        self._sounds: dict[str, pygame.mixer.Sound] = {}
        self._load_lock = Lock()
        self._note_channels: dict[int, pygame.mixer.Channel] = {}
        self._max_play_timers: dict[int, Timer] = {}
        # Retrigger lockout keyed by sample path so the same sample can't replay
        # within cooldown even if triggered from a different pad.
        self._last_sample_trigger: dict[str, float] = {}
        # Avoid picking the same sample twice in a row from the same group on
        # the same pad (when the group has >= 2 samples).
        self._last_pick_per_pad: dict[int, str] = {}

    # ── lifecycle ──────────────────────────────────────────────────────────
    def init(self):
        pygame.mixer.pre_init(frequency=SAMPLE_RATE, size=-16, channels=2, buffer=BUFFER_SIZE)
        pygame.mixer.init()
        pygame.mixer.set_num_channels(NUM_CHANNELS)
        log.info("Sampler initialized: %d Hz, %d channels", SAMPLE_RATE, NUM_CHANNELS)

    # ── discovery ──────────────────────────────────────────────────────────
    def list_groups(self) -> list[str]:
        if not self.samples_dir.exists():
            return []
        out = []
        for p in sorted(self.samples_dir.iterdir()):
            if p.is_dir() and any(c.suffix.lower() in (".wav", ".ogg") for c in p.iterdir()):
                out.append(p.name)
        return out

    def list_group_samples(self, group: str) -> list[Path]:
        gdir = self.samples_dir / group
        if not gdir.is_dir():
            return []
        return sorted(p for p in gdir.iterdir() if p.suffix.lower() in (".wav", ".ogg"))

    def total_sample_count(self) -> int:
        return sum(len(self.list_group_samples(g)) for g in self.list_groups())

    # ── audio cache ────────────────────────────────────────────────────────
    def _load(self, path: Path) -> pygame.mixer.Sound | None:
        key = str(path)
        with self._load_lock:
            if key in self._sounds:
                return self._sounds[key]
            if not path.exists():
                log.warning("Sample missing: %s", path)
                return None
            try:
                sound = pygame.mixer.Sound(key)
            except pygame.error as exc:
                log.error("Failed to load %s: %s", path, exc)
                return None
            self._sounds[key] = sound
            return sound

    def preload_all(self):
        count = 0
        for group in self.list_groups():
            for sample in self.list_group_samples(group):
                if self._load(sample) is not None:
                    count += 1
        log.info("Preloaded %d samples across %d groups", count, len(self.list_groups()))

    def invalidate(self):
        with self._load_lock:
            self._sounds.clear()

    # ── playback ───────────────────────────────────────────────────────────
    def _pick_sample(self, note: int, group: str) -> Path | None:
        samples = self.list_group_samples(group)
        if not samples:
            return None
        if len(samples) == 1:
            return samples[0]
        last = self._last_pick_per_pad.get(note)
        candidates = [s for s in samples if str(s) != last] or samples
        return random.choice(candidates)

    def _cancel_max_timer(self, note: int):
        t = self._max_play_timers.pop(note, None)
        if t is not None:
            t.cancel()

    def play_note(self, note: int, velocity: int = 127, forced_group: str | None = None):
        pad = self.config.pad(note)
        group = forced_group or pad.get("group")
        if not group:
            return

        sample_path = self._pick_sample(note, group)
        if sample_path is None:
            log.debug("group %r is empty for pad %d", group, note)
            return

        # Retrigger lockout: per-sample
        cooldown = float(self.config.get_global("retrigger_cooldown_seconds", 2.0))
        now = time.monotonic()
        key = str(sample_path)
        last = self._last_sample_trigger.get(key, 0.0)
        if now - last < cooldown:
            log.debug("retrigger lockout: %s (%.2fs left)", sample_path.name, cooldown - (now - last))
            return
        self._last_sample_trigger[key] = now
        self._last_pick_per_pad[note] = key

        sound = self._load(sample_path)
        if sound is None:
            return

        master = self.config.master_volume
        vol = float(pad.get("volume", 1.0)) * master
        sound.set_volume(max(0.0, min(1.0, vol)))

        hold = bool(pad.get("hold", True))
        loops = -1 if hold else 0

        prev = self._note_channels.get(note)
        if prev is not None and prev.get_busy():
            prev.stop()
        self._cancel_max_timer(note)

        channel = sound.play(loops=loops)
        if channel is None:
            return
        self._note_channels[note] = channel

        # Record for UI display
        self.config.set_last_play(note, sample_path.name, group)
        log.info("play note=%d group=%s sample=%s vol=%.2f hold=%s",
                 note, group, sample_path.name, vol, hold)

        # Schedule auto-fadeout at max_play_seconds
        max_play = float(self.config.get_global("max_play_seconds", 20.0))
        release_ms = int(self.config.get_global("release_fade_ms", 5000))
        timer = Timer(max_play, self._auto_release, args=(note, release_ms))
        timer.daemon = True
        timer.start()
        self._max_play_timers[note] = timer

    def release_note(self, note: int):
        """Called on MIDI note_off — fade out only when pad is in hold mode."""
        pad = self.config.pad(note)
        if not pad.get("hold", True):
            return
        release_ms = int(self.config.get_global("release_fade_ms", 5000))
        self._fadeout_note(note, release_ms)

    def _auto_release(self, note: int, fade_ms: int):
        log.debug("max-play cap reached for note %d, fading out (%d ms)", note, fade_ms)
        self._fadeout_note(note, fade_ms)

    def _fadeout_note(self, note: int, fade_ms: int):
        ch = self._note_channels.get(note)
        if ch is not None and ch.get_busy():
            ch.fadeout(max(1, fade_ms))
        self._cancel_max_timer(note)

    def stop_all(self):
        pygame.mixer.stop()
        for t in list(self._max_play_timers.values()):
            t.cancel()
        self._max_play_timers.clear()
