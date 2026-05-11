"""Entry point: starts sampler, MIDI listener, and Flask config UI in one process."""
from __future__ import annotations
import argparse
import logging
import os
import signal
import sys
from pathlib import Path

from config import Config
from sampler import Sampler
from midi_listener import MidiListener
from server import create_app


def parse_args():
    p = argparse.ArgumentParser(description="Playtronica TouchMe → sample player")
    p.add_argument("--samples", default=os.environ.get("PLAYTRONICA_SAMPLES", "samples/wav"),
                   help="Directory with .wav samples")
    p.add_argument("--config", default=os.environ.get("PLAYTRONICA_CONFIG", "app/config.json"),
                   help="Path to config.json")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--midi-hint", default=os.environ.get("PLAYTRONICA_MIDI_HINT", "TouchMe"))
    p.add_argument("--debug", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    log = logging.getLogger("playtronica")

    samples_dir = Path(args.samples).resolve()
    config_path = Path(args.config).resolve()
    samples_dir.mkdir(parents=True, exist_ok=True)

    log.info("Starting Playtronica TouchMe Art")
    log.info("  samples dir: %s", samples_dir)
    log.info("  config:      %s", config_path)
    log.info("  midi hint:   %s", args.midi_hint)

    config = Config(config_path)
    sampler = Sampler(samples_dir, config)
    sampler.init()
    sampler.preload_all()

    midi = MidiListener(sampler, device_hint=args.midi_hint)
    midi.start()

    def shutdown(signum, _frame):
        log.info("Signal %d — shutting down", signum)
        midi.stop()
        sampler.stop_all()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    app = create_app(config, sampler, midi, samples_dir)
    log.info("Web UI: http://%s:%d", args.host, args.port)
    app.run(host=args.host, port=args.port, debug=args.debug, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
