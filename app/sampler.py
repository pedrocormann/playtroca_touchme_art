"""Polyphonic sample player with per-sample retrigger lockout, hold-to-play,
release fade-out, and a hard max-play cap."""
from __future__ import annotations
import logging
import threading
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
        # Per-note state
        self._note_channels: dict[int, pygame.mixer.Channel] = {}
        self._max_play_timers: dict[int, Timer] = {}
        # Per-sample state (retrigger lockout shared across pads playing same file)
        self._last_sample_trigger: dict[str, float] = {}

    def init(self):
        pygame.mixer.pre_init(frequency=SAMPLE_RATE, size=-16, channels=2, buffer=BUFFER_SIZE)
        pygame.mixer.init()
        pygame.mixer.set_num_channels(NUM_CHANNELS)
        log.info("Sampler initialized: %d Hz, %d channels", SAMPLE_RATE, NUM_CHANNELS)

    def list_samples(self) -> list[str]:
        if not self.samples_dir.exists():
            return []
        return sorted(p.name for p in self.samples_dir.iterdir() if p.suffix.lower() in (".wav", ".ogg"))

    def _load(self, filename: str) -> pygame.mixer.Sound | None:
        with self._load_lock:
            if filename in self._sounds:
                return self._sounds[filename]
            path = self.samples_dir / filename
            if not path.exists():
                log.warning("Sample missing: %s", path)
                return None
            try:
                sound = pygame.mixer.Sound(str(path))
            except pygame.error as exc:
                log.error("Failed to load %s: %s", path, exc)
                return None
            self._sounds[filename] = sound
            return sound

    def preload_all(self):
        for name in self.list_samples():
            self._load(name)
        log.info("Preloaded %d samples", len(self._sounds))

    def _cancel_max_timer(self, note: int):
        t = self._max_play_timers.pop(note, None)
        if t is not None:
            t.cancel()

    def play_note(self, note: int, velocity: int = 127):
        pad = self.config.pad(note)
        filename = pad.get("file")
        if not filename:
            return
        # Retrigger lockout (per sample, shared across pads playing the same file)
        cooldown = float(self.config.get_global("retrigger_cooldown_seconds", 2.0))
        now = time.monotonic()
        last = self._last_sample_trigger.get(filename, 0.0)
        if now - last < cooldown:
            log.debug("retrigger lockout: %s (%.2fs left)", filename, cooldown - (now - last))
            return
        self._last_sample_trigger[filename] = now

        sound = self._load(filename)
        if sound is None:
            return

        master = self.config.master_volume
        vol = float(pad.get("volume", 1.0)) * master
        sound.set_volume(max(0.0, min(1.0, vol)))

        hold = bool(pad.get("hold", True))
        loops = -1 if hold else 0

        # Stop any previous voice on this note (no fade — we're retriggering)
        prev = self._note_channels.get(note)
        if prev is not None and prev.get_busy():
            prev.stop()
        self._cancel_max_timer(note)

        channel = sound.play(loops=loops)
        if channel is None:
            return
        self._note_channels[note] = channel
        log.debug("play note=%d file=%s vol=%.2f hold=%s", note, filename, vol, hold)

        # Schedule auto-fadeout at max_play_seconds
        max_play = float(self.config.get_global("max_play_seconds", 20.0))
        release_ms = int(self.config.get_global("release_fade_ms", 5000))
        timer = Timer(max_play, self._auto_release, args=(note, release_ms))
        timer.daemon = True
        timer.start()
        self._max_play_timers[note] = timer

    def release_note(self, note: int):
        """Called on MIDI note_off — fade out only for pads in hold mode."""
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
        for note, t in list(self._max_play_timers.items()):
            t.cancel()
        self._max_play_timers.clear()

    def invalidate(self, filename: str | None = None):
        with self._load_lock:
            if filename is None:
                self._sounds.clear()
            else:
                self._sounds.pop(filename, None)
