# Adafruit-matrix-led-to-octoprint-conection
Files necesary to display octoprint job and printer info on a matrix led (32x64) via api key

  Ai was used in the project (GLM 5.3 - MAX)


#To config
  Execute the data sending file using
    python octoprint_to_matrix.py --url http://YOUR OCTOPRINT URL --key YOUR API KEY (Has to be in the same network and/or device as the octoprint server)
    python octoprint_to_matrix.py --demo                  no OctoPrint needed
    python octoprint_to_matrix.py --port COM7 ...         skip auto-detect

# OctoPrint Matrix Status

![CircuitPython](https://img.shields.io/badge/CircuitPython-Matrix%20Portal%20M4-blueviolet)
![Python 3](https://img.shields.io/badge/Python-3-blue)
![No libraries](https://img.shields.io/badge/libraries-none-brightgreen)

Live print status from OctoPrint on a 32×64 RGB LED matrix, driven by an
Adafruit Matrix Portal M4.

One fixed screen — no rotating pages, no `.bdf` font files, no external
CircuitPython libraries. The board side uses only modules built into
CircuitPython; the host side needs nothing but Python 3 + `pyserial`.

<!-- Add a photo of your build: -->
<!-- ![build photo](docs/photo.jpg) -->

```text
┌────────────────────────────────────────────────────────────┐
│ 45% 1h05                                                   │
│                                                            │
│ N212/215                                                   │
│                                                            │
│ B60/60                                                     │
│                                                            │
│ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
└────────────────────────────────────────────────────────────┘
```

## Features

- **One fixed screen, always** — status line, nozzle temp, bed temp, progress
  bar; the layout never changes or rotates
- **State color coding** — green = printing, amber = paused, cyan = done,
  red = error, gray = offline…
- **Percent + compact ETA** (`45m`, `1h05`) while printing
- **Auto port detection** — the sender finds the Matrix Portal by USB vendor
  ID + `PING`/`PONG` handshake; works on Windows and Linux unchanged
- **No fonts to install** — a 5×7 pixel font is embedded in `code.py`;
  text is drawn pixel-exact, so lines can never drift or misplace
- **Brightness control** by RGB scaling (the correct way to dim HUB75 panels)
- **Crash-safe** — any board-side error is printed to serial, written to
  `CIRCUITPY/error.txt`, and shown as `CRASH` on the matrix
- **Link watchdog** — shows `NOHOST` after 10 s without serial data
- **Demo mode** to test the display without an OctoPrint server
- **systemd unit** included for Raspberry Pi autostart

## Hardware

| Part | Notes |
|------|-------|
| Adafruit Matrix Portal M4 | plugs straight onto the panel's HUB75 input |
| 32×64 RGB LED matrix, HUB75 | the standard Adafruit 64×32 panel works as-is |
| USB cable (data) | PC or Raspberry Pi → Matrix Portal |
| *Optional:* 5 V ≥ 2 A supply | into the Matrix Portal screw terminal, if USB power is marginal |

> A single 32×64 panel normally runs fine off USB power. If the board reboots or
> the panel dims, feed 5 V into the screw terminal — USB stays connected for data.

## How it works

```text
OctoPrint REST API ──► octoprint_to_matrix.py ──USB serial──► code.py ──► 32×64 panel
                        (Windows PC or Pi)                    (Matrix Portal M4)
```

The host polls OctoPrint every 2 s and pushes a few short lines
(`S=PRINTING`, `P=42`, `E=1h05`, `N=212/215`, `B=60/60`) over USB CDC serial.
The board parses them and renders the fixed screen.

## Repository contents

```text
├── code.py                    # runs ON the Matrix Portal M4 (CircuitPython)
├── octoprint_to_matrix.py     # runs on the host: Windows PC or Raspberry Pi
└── README.md
```

## Setup

### 1. Matrix Portal M4

1. Flash the board with CircuitPython for Matrix Portal M4 if you haven't already.
2. Copy `code.py` to the `CIRCUITPY` drive.
3. That's it — **no libraries need to go into `lib/`**; only built-in modules
   are used.

Within a few seconds the panel should show `WAITING`, `N--`, `B--` and an
empty progress bar.

### 2. Host (Windows PC or Raspberry Pi)

```bash
pip install pyserial          # Windows: py -m pip install pyserial
                              # Raspberry Pi OS: sudo apt install python3-serial
```

Generate an API key in OctoPrint: **Settings → Application Keys** (read access
is all this needs).

Run it:

```bash
# Windows (an IP is more reliable than octopi.local there)
py octoprint_to_matrix.py --url http://192.168.1.42 --key YOUR_API_KEY

# Raspberry Pi (OctoPrint on the same machine)
python3 octoprint_to_matrix.py --url http://127.0.0.1:5000 --key YOUR_API_KEY
```

The serial port is detected automatically. On Linux the user needs to be in
the `dialout` group (`sudo usermod -aG dialout $USER`, then re-login).

## Usage

```text
usage: octoprint_to_matrix.py [-h] [--url URL] [--key KEY]
                              [--port PORT] [--interval SECONDS] [--demo]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--url` | `http://octopi.local` | OctoPrint base URL |
| `--key` | — (required) | OctoPrint application API key |
| `--port` | auto | serial port of the Matrix Portal; found via `PING`/`PONG` |
| `--interval` | `2.0` | poll interval in seconds |
| `--demo` | off | simulate a full print; no OctoPrint needed |

**Test without a printer:** `python3 octoprint_to_matrix.py --demo`
runs a fake IDLE → heat-up → print → DONE cycle on the matrix.

**Manual test:** open any serial terminal on the board's port and type lines
yourself: `S=PRINTING`, `P=42`, `E=1h05`, `N=212/215`, `B=60/60`.
(Close Mu/Thonny/PuTTY first — only one program can hold the port.)

## Autostart on Raspberry Pi

```bash
sudo mkdir -p /opt/octoprint-matrix
sudo cp octoprint_to_matrix.py /opt/octoprint-matrix/
sudo nano /etc/systemd/system/matrix-bridge.service
```

```ini
[Unit]
Description=OctoPrint to Matrix Portal status bridge
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
ExecStart=/usr/bin/python3 /opt/octoprint-matrix/octoprint_to_matrix.py \
    --url http://127.0.0.1:5000 --key YOUR_API_KEY
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now matrix-bridge
journalctl -u matrix-bridge -f        # live log
```

## Screen layout (64×32)

```text
y  0– 6   status line    "45% 1h05" while printing, otherwise the state word
y  7– 8   blank
y  9–15   nozzle         "N212/215"  (actual/target, or actual only)
y 16–17   blank
y 18–24   bed            "B60/60"
y 25      blank          (1 px margin)
y 26–31   progress bar   fill color follows the state color
```

## States & colors

| State | Color | Meaning |
|-------|-------|---------|
| `PRINTING` | green | print in progress |
| `PAUSED` | amber | paused |
| `DONE` | cyan | print finished |
| `IDLE` | dim white | printer connected, doing nothing |
| `STOPPED` | orange | print cancelled |
| `ERROR` | red | printer error |
| `OFFLINE` | gray | OctoPrint unreachable / printer not connected |
| `NOHOST` | gray | no serial data from the host for 10 s |
| `WAITING` | dark gray | board just booted |

## Serial protocol

Line-based, ASCII, `\n`-terminated. Sent by the host:

| Line | Meaning | Example |
|------|---------|---------|
| `S=<state>` | one of the states above | `S=PRINTING` |
| `P=<percent>` | 0–100 | `P=42` |
| `E=<eta>` | ≤4 chars | `E=1h05` |
| `N=<nozzle>` | `actual` or `actual/target` | `N=212/215` |
| `B=<bed>` | same format | `B=60/60` |
| `PING` | port-detection probe → board replies `PONG\n` | |

Unknown keys and malformed lines are ignored, so the protocol is trivially
extensible (e.g. add `L=` for layer count).

## Customization

Everything lives in constants at the top of `code.py`:

| Constant | Effect |
|----------|--------|
| `BRIGHTNESS` | 0.0–1.0; scales every color per channel. `0.5` ≈ half, `0.3` = night mode |
| `BIT_DEPTH` | 2–4; lower if the panel flickers, raise for smoother dim colors |
| `HOST_TIMEOUT` | seconds of serial silence before `NOHOST` |
| `STATE_COLORS`, `NOZZLE_COLOR`, `BED_COLOR`, `BAR_TRACK` | `0xRRGGBB` colors |
| `ROW_YS`, `BAR_Y`, `BAR_H` | pixel geometry of the screen |

The embedded 5×7 font is plain data — each glyph is 7 binary rows, top row
first, leftmost pixel = highest bit, so you can literally read/edit letters:

```python
"L": (0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b11111),
```

Unknown characters render blank; unknown lowercase falls back to uppercase.
The font covers digits, `A–Z`, `% + - . / : !` and `h`/`m`.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Board shows `CRASH` | open `CIRCUITPY/error.txt` — full traceback is in there |
| `HTTP 401` in host log | wrong API key |
| `Matrix Portal not found` | check the cable; pin the port manually with `--port COM7` / `--port /dev/ttyACM0` |
| Host can't open port (Windows) | close Mu/Thonny/PuTTY first |
| Host can't open port (Linux) | add your user to `dialout` and re-login |
| Board keeps rebooting / panel dims | undervoltage — use the screw-terminal 5 V input; lowering `BRIGHTNESS` also reduces current draw |
| Panel flickers | lower `BIT_DEPTH` to 2 |
| Weird serial garbage on some Linux distros | `sudo apt purge modemmanager`, then replug |

## Ideas / roadmap

- More data on screen: layer count, elapsed time, filament used (just add a
  protocol letter)
- Event-driven updates via OctoPrint's websocket instead of 2 s polling
- Multi-extruder temperatures
- Scroll long filenames across the status line when idle

## License
