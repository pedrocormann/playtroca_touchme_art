"""Flask config UI — accessible from any device on the local network."""
from __future__ import annotations
import logging
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

log = logging.getLogger(__name__)


def create_app(config, sampler, midi_listener, samples_dir: Path) -> Flask:
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/config", methods=["GET"])
    def get_config():
        return jsonify(config.snapshot())

    @app.route("/api/pad/<int:note>", methods=["POST"])
    def update_pad(note: int):
        data = request.get_json(force=True) or {}
        config.update_pad(note, data)
        # sample changed? drop cache so next play reloads
        if "file" in data:
            sampler.invalidate()
        return jsonify({"ok": True, "pad": config.pad(note)})

    @app.route("/api/master", methods=["POST"])
    def set_master():
        data = request.get_json(force=True) or {}
        if "volume" in data:
            config.set_global("master_volume", max(0.0, min(1.0, float(data["volume"]))))
        return jsonify({"ok": True, "master_volume": config.master_volume})

    @app.route("/api/global", methods=["POST"])
    def set_globals():
        data = request.get_json(force=True) or {}
        applied = {}
        for k in ("retrigger_cooldown_seconds", "release_fade_ms", "max_play_seconds", "master_volume"):
            if k in data:
                config.set_global(k, float(data[k]))
                applied[k] = config.get_global(k)
        return jsonify({"ok": True, "applied": applied})

    @app.route("/api/samples", methods=["GET"])
    def list_samples():
        return jsonify({"samples": sampler.list_samples()})

    @app.route("/api/test/<int:note>", methods=["POST"])
    def test_note(note: int):
        sampler.play_note(note)
        return jsonify({"ok": True})

    @app.route("/api/stop", methods=["POST"])
    def stop_all():
        sampler.stop_all()
        return jsonify({"ok": True})

    @app.route("/api/status", methods=["GET"])
    def status():
        return jsonify({
            "midi_port": midi_listener.port_name,
            "samples_dir": str(samples_dir),
            "sample_count": len(sampler.list_samples()),
        })

    @app.route("/audio/<path:filename>")
    def serve_audio(filename: str):
        return send_from_directory(samples_dir, filename, as_attachment=False)

    return app
