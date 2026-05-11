# Playtronica TouchMe Art

> A small interactive sound system built in ~2 hours for the artist
> **[Osvaldo Eugênio (@osvaldin_the_cre8tor_iltda_)](https://www.instagram.com/osvaldin_the_cre8tor_iltda_/)**,
> for the exhibition **"Vai Tomando"** at **Museu Futuros**, Rio de Janeiro.

Visitors touch copper wires running out of stones that the artist embedded with
circuits as aesthetic interventions. A [Playtronica TouchMe](https://playtronica.com/products/touchme)
reads the capacitive contact and emits MIDI; a Raspberry Pi running this code
translates each touch into one of many short audio fragments curated by the
artist, organized into groups (textural / percussive / breath / etc.).

The mapping from pad → group is randomized: every reboot (and on demand) the
algorithm shuffles which sound family responds to which sensor, so the piece
never sounds the same way twice. Within a group, the played sample is also
randomly selected, but the same sample won't repeat too quickly.

## Architecture

```
 copper wire (visitor touch)  →  TouchMe (USB MIDI)  →  Raspberry Pi 4
                                                          │
                                                ┌─────────┴──────────┐
                                                │                    │
                                        midi_listener.py      Flask (port 8080)
                                                │                    │
                                                ▼                    ▼
                                          sampler.py          config UI / API
                                       (pygame.mixer)                │
                                                │                    │
                                                ▼                    │
                                       3.5 mm jack  ←─ headphones / PA system
                                                          ▲
                                                          │
                                                       config.json
```

A single Python process orchestrates:

- **midi_listener** — listens to the TouchMe over ALSA MIDI, dispatches
  `play_note` / `release_note`
- **sampler** — polyphonic `pygame.mixer` (16 channels) with per-sample
  retrigger lockout, hold-to-play, release fade-out, and a hard cap on
  per-touch duration
- **server** — Flask UI on `http://<pi-ip>:8080` for live tuning of all
  parameters; configuration persists in `config.json`

The service starts automatically on boot through systemd; the Pi also boots
straight into Chromium fullscreen showing the configuration UI. No display is
required to run the installation — every parameter is reachable over the LAN.

## Behavior

- **groups of samples**: each TouchMe pad is assigned to a *group* (a folder of
  short WAVs). When the pad fires, one sample is picked at random from the
  group; consecutive picks on the same pad avoid repeating the previous sample.
- **automatic mapping**: on first run (and via the *Shuffle groups* button) the
  app round-robins all available groups across the 12 pads, with a random
  permutation. The artist never has to manually wire pad → sample.
- **hold-to-play** (default on): while the visitor is touching, audio plays;
  on release it fades out over 5 s.
- **retrigger lockout**: the same sample cannot fire again within N seconds
  (default 2 s) — prevents nervous "remixing" when visitors tap rapidly.
- **per-touch cap**: a single playback never exceeds 20 s, even if the visitor
  keeps holding (auto fade-out at the cap).
- **always at maximum volume**: a dedicated `audio-max.service` raises Master,
  PCM and Headphone to 100 % on every boot.

All of the above is live-editable in the web UI.

## Sample pipeline

Drop source files (any of `mp3`, `wav`, `flac`, `ogg`, `m4a`, `aac`, `opus`)
into `samples/sources/<group>/`. The build script:

1. trims leading and trailing silence (≥ 0.3 s under −45 dB)
2. resamples to 44.1 kHz / 16-bit stereo
3. splits into 30-second chunks (configurable via `CHUNK_SECONDS`)
4. applies a 50 ms fade-in on each chunk to avoid clicks

Output lands in `samples/wav/<group>/<source-stem>_NNN.wav`. The script is
idempotent — sources whose first chunk is newer than the source are skipped.

## Deploy

```bash
# from your laptop, with SSH access to the Pi configured as the "playtronica"
# host in your ~/.ssh/config:
tools/deploy.sh           # rsync code + samples, build chunks, restart service
tools/deploy.sh --code    # code only (skip the audio sources; faster iteration)
```

`tools/install_pi.sh` runs on the Pi each deploy and is idempotent. It:

- installs the system packages (`puredata`, `ffmpeg`, `python3-pygame`,
  `python3-rtmidi`, `python3-flask`)
- creates a venv at `/opt/playtronica/venv` inheriting the apt-installed
  C-extensions, then `pip install mido`
- builds the sample chunks
- installs `playtronica.service` (the app) and `audio-max.service`
- installs the kiosk autostart entry under `~/.config/autostart/`
- disables screen blanking

## Useful commands on the Pi

```bash
sudo journalctl -u playtronica -f      # live logs from the sampler
sudo systemctl restart playtronica     # restart the service
pkill chromium                         # exit the kiosk; desktop returns
sudo amixer sset Master 100% unmute    # re-apply max volume (audio-max also does this)
```

## Hardware

- Raspberry Pi 4 Model B (4 GB) — Raspberry Pi OS Bookworm
- Playtronica TouchMe — USB MIDI (class compliant), 12 capacitive inputs
- Audio out: 3.5 mm jack (`card 1: bcm2835 Headphones`)
- Display optional (only needed at install time; the kiosk uses it if present)

## Stack

Python 3.11 · Flask · `mido` · `python-rtmidi` · `pygame.mixer` · `ffmpeg` ·
ALSA · systemd · Chromium kiosk.

## Roadmap (V2)

- TouchMe in **CC mode** (continuous capacitance instead of discrete notes),
  reconfigured via Playtronica's PlayDuo desktop app, mapped to real-time
  volume / parameter modulation
- real-time effects chain (filter / saturation / reverb), e.g. via `pyo` or
  Pure Data (Pd is already installed on the Pi as a fallback engine)
- per-group dynamics (loudness normalization, per-group gain)
- multi-Pi sync for spatialized stones across a larger room

## Credits

Software, sampler design and Pi setup: **[Pedro Cormann](https://github.com/pedrocormann) (Unflat Studio)**,
with assistance from Claude Code. Original audio material, conceptual direction
and stone-and-copper sculpture: **Osvaldo Eugênio**.

Built in May 2026 — about two hours from empty repo to working installation.
