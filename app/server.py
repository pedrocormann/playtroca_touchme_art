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
        snap = config.snapshot()
        # decorate pads with last-played info for the UI
        last = config.all_last_plays()
        for n_str, pad in snap.get("pads", {}).items():
            pad["last_play"] = last.get(int(n_str))
        snap["groups"] = sampler.list_groups()
        return jsonify(snap)

    @app.route("/api/groups", methods=["GET"])
    def list_groups():
        groups = sampler.list_groups()
        detail = {g: [p.name for p in sampler.list_group_samples(g)] for g in groups}
        return jsonify({"groups": groups, "samples_by_group": detail})

    @app.route("/api/pad/<int:note>", methods=["POST"])
    def update_pad(note: int):
        data = request.get_json(force=True) or {}
        config.update_pad(note, data)
        return jsonify({"ok": True, "pad": config.pad(note)})

    @app.route("/api/global", methods=["POST"])
    def set_globals():
        data = request.get_json(force=True) or {}
        applied = {}
        for k in ("retrigger_cooldown_seconds", "release_fade_ms", "max_play_seconds", "master_volume"):
            if k in data:
                config.set_global(k, float(data[k]))
                applied[k] = config.get_global(k)
        return jsonify({"ok": True, "applied": applied})

    @app.route("/api/test/<int:note>", methods=["POST"])
    def test_note(note: int):
        sampler.play_note(note)
        last = config.get_last_play(note)
        return jsonify({"ok": True, "last_play": last})

    @app.route("/api/stop", methods=["POST"])
    def stop_all():
        sampler.stop_all()
        return jsonify({"ok": True})

    @app.route("/api/status", methods=["GET"])
    def status():
        last = config.all_last_plays()
        return jsonify({
            "midi_port": midi_listener.port_name,
            "samples_dir": str(samples_dir),
            "groups": sampler.list_groups(),
            "sample_count": sampler.total_sample_count(),
            "last_plays": {str(n): v for n, v in last.items()},
        })

    @app.route("/audio/<path:filename>")
    def serve_audio(filename: str):
        return send_from_directory(samples_dir, filename, as_attachment=False)

    return app
