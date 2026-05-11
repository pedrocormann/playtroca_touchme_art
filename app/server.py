"""Flask config UI — accessible from any device on the local network."""
from __future__ import annotations
import logging
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

log = logging.getLogger(__name__)


def create_app(config, sampler, midi_listener, samples_dir: Path, presets=None) -> Flask:
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    from preset_manager import PRESET_KEYS

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
        # master_volume is intentionally read-only on the Pi (always 1.0)
        for k in ("retrigger_cooldown_seconds", "release_fade_ms", "max_play_seconds"):
            if k in data:
                config.set_global(k, float(data[k]))
                applied[k] = config.get_global(k)
        return jsonify({"ok": True, "applied": applied})

    # ── presets ───────────────────────────────────────────────────────────
    @app.route("/api/presets", methods=["GET"])
    def list_presets():
        return jsonify({"presets": presets.list() if presets else []})

    @app.route("/api/presets", methods=["POST"])
    def save_preset():
        if presets is None:
            return jsonify({"ok": False, "error": "presets disabled"}), 400
        body = request.get_json(silent=True) or {}
        # Snapshot the current playback-behavior globals
        values = {k: config.get_global(k) for k in PRESET_KEYS}
        try:
            entry = presets.save(values, name=body.get("name"))
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "preset": entry})

    @app.route("/api/presets/<name>/load", methods=["POST"])
    def load_preset(name: str):
        if presets is None:
            return jsonify({"ok": False, "error": "presets disabled"}), 400
        data = presets.get(name)
        if data is None:
            return jsonify({"ok": False, "error": "not found"}), 404
        applied = {}
        for k in PRESET_KEYS:
            if k in data:
                config.set_global(k, float(data[k]))
                applied[k] = config.get_global(k)
        return jsonify({"ok": True, "applied": applied})

    @app.route("/api/presets/<name>", methods=["DELETE"])
    def delete_preset(name: str):
        if presets is None:
            return jsonify({"ok": False, "error": "presets disabled"}), 400
        ok = presets.delete(name)
        return jsonify({"ok": ok})

    @app.route("/api/test/<int:note>", methods=["POST"])
    def test_note(note: int):
        sampler.play_note(note)
        last = config.get_last_play(note)
        return jsonify({"ok": True, "last_play": last})

    @app.route("/api/stop", methods=["POST"])
    def stop_all():
        sampler.stop_all()
        return jsonify({"ok": True})

    @app.route("/api/shuffle", methods=["POST"])
    def shuffle_groups():
        data = request.get_json(silent=True) or {}
        # Default: keep dark→bright ordering. Pass {"random": true} for chaos.
        respect = not bool(data.get("random", False))
        groups = sampler.list_groups()
        config.auto_assign_groups(groups, force=True, respect_order=respect)
        return jsonify({"ok": True, "pads": config.snapshot()["pads"]})

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
