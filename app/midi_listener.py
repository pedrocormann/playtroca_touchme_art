"""ALSA MIDI input listener — auto-finds TouchMe and routes notes to the Sampler."""
from __future__ import annotations
import logging
import threading
import time

import mido

log = logging.getLogger(__name__)

DEFAULT_DEVICE_HINT = "TouchMe"


class MidiListener(threading.Thread):
    def __init__(self, sampler, device_hint: str = DEFAULT_DEVICE_HINT):
        super().__init__(daemon=True, name="MidiListener")
        self.sampler = sampler
        self.device_hint = device_hint
        self._stop = threading.Event()
        self._port_name: str | None = None

    @property
    def port_name(self) -> str | None:
        return self._port_name

    def stop(self):
        self._stop.set()

    def _find_port(self) -> str | None:
        try:
            names = mido.get_input_names()
        except Exception as exc:
            log.error("mido.get_input_names() failed: %s", exc)
            return None
        for n in names:
            if self.device_hint.lower() in n.lower():
                return n
        return None

    def run(self):
        log.info("MIDI listener started, looking for '%s'", self.device_hint)
        while not self._stop.is_set():
            port_name = self._find_port()
            if port_name is None:
                log.info("Waiting for %s MIDI device...", self.device_hint)
                time.sleep(2)
                continue
            self._port_name = port_name
            log.info("Connected to MIDI input: %s", port_name)
            try:
                with mido.open_input(port_name) as port:
                    for msg in port:
                        if self._stop.is_set():
                            break
                        self._handle(msg)
            except Exception as exc:
                log.warning("MIDI port error (%s): %s — retrying in 2s", port_name, exc)
                self._port_name = None
                time.sleep(2)
        log.info("MIDI listener stopped")

    def _handle(self, msg):
        if msg.type == "note_on" and msg.velocity > 0:
            log.debug("note_on note=%d vel=%d", msg.note, msg.velocity)
            self.sampler.play_note(msg.note, velocity=msg.velocity)
        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            log.debug("note_off note=%d", msg.note)
            self.sampler.release_note(msg.note)
