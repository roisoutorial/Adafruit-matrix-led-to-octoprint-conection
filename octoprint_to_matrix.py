#!/usr/bin/env python3
# octoprint_to_matrix.py -- run on the PC now, unchanged on the Pi 4 later.
#
# Polls OctoPrint's REST API and pushes a compact status to the Matrix
# Portal M4 over USB serial.
#
#   pip install pyserial
#   API key: OctoPrint -> Settings -> Application Keys -> Generate
#            (older OctoPrint: Settings -> API -> Global API Key)
#
#   python octoprint_to_matrix.py --url http://192.168.1.42 --key XXXXX
#   python octoprint_to_matrix.py --demo                 # no OctoPrint needed
#   python octoprint_to_matrix.py --port COM7 ...        # skip auto-detect

import argparse
import json
import time
import urllib.error
import urllib.request

import serial
import serial.tools.list_ports

BAUD      = 115200   # ignored by USB CDC; pyserial just wants a number
ADA_VID   = 0x239A   # Adafruit USB vendor ID -> finds CircuitPython boards
PING_WAIT = 1.0      # seconds to wait for PONG while scanning ports


# ---------------------------------------------------------------- serial --

def find_matrix_port():
    """Ask every Adafruit USB serial port for a PONG; return the device name."""
    for info in serial.tools.list_ports.comports():
        if info.vid != ADA_VID:
            continue
        try:
            with serial.Serial(info.device, BAUD, timeout=0.3) as s:
                s.reset_input_buffer()
                s.write(b"PING\n")
                got, deadline = b"", time.time() + PING_WAIT
                while time.time() < deadline and b"PONG" not in got:
                    got += s.read(32)
                if b"PONG" in got:
                    return info.device
        except (serial.SerialException, OSError):
            continue
    return None


# -------------------------------------------------------------- octoprint --

def api_get(url, key, path):
    req = urllib.request.Request(url.rstrip("/") + path,
                                 headers={"X-Api-Key": key})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def map_state(s):
    s = (s or "").strip().lower()
    if s.startswith("printing"):    return "PRINTING"
    if s.startswith("paused"):      return "PAUSED"
    if s.startswith("operational"): return "IDLE"
    if s.startswith("complete"):    return "DONE"
    if s.startswith("cancel"):      return "STOPPED"
    if s.startswith("error"):       return "ERROR"
    if s.startswith("offline"):     return "OFFLINE"
    return (s or "?")[:8].upper()


def fmt_eta(seconds):
    """Compact ETA for the 8-char display line: 45m / 1h05 / 12h / 99h+ / --"""
    if not seconds or seconds < 0:
        return "--"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    if h >= 100:
        return "99h+"
    if h >= 10:
        return "%dh" % h
    if h >= 1:
        return "%dh%02d" % (h, m)
    return "%02dm" % m


def fmt_temp(t):
    if not t or t.get("actual") is None:
        return "--"
    actual = int(round(t["actual"]))
    target = t.get("target") or 0
    if target > 0:
        return "%d/%d" % (actual, int(round(target)))
    return "%d" % actual


def poll(url, key):
    """One snapshot -> (state, pct, eta, nozzle, bed). Raises on HTTP problems."""
    job = api_get(url, key, "/api/job")
    try:
        printer = api_get(url, key, "/api/printer")
    except urllib.error.HTTPError as e:
        if e.code == 409:          # printer not connected to OctoPrint right now
            printer = None
        else:
            raise

    state = map_state(job.get("state"))
    prog = job.get("progress") or {}
    comp = prog.get("completion")
    pct = int(round(comp)) if comp is not None else 0
    eta = fmt_eta(prog.get("printTimeLeft"))

    if printer is None:
        state, nozzle, bed = "OFFLINE", "--", "--"
    else:
        temps = printer.get("temperature") or {}
        nozzle = fmt_temp(temps.get("tool0"))
        bed = fmt_temp(temps.get("bed"))
    return state, pct, eta, nozzle, bed


# ------------------------------------------------------------------- send --

def send(ser, state, pct, eta, nozzle, bed):
    ser.write(("S=%s\nP=%d\nE=%s\nN=%s\nB=%s\n"
               % (state, pct, eta, nozzle, bed)).encode("ascii"))


def demo(ser):
    """Fake print data so you can check the matrix without OctoPrint."""
    print("Demo mode (Ctrl+C to quit): IDLE -> heatup -> print -> DONE ...")
    while True:
        send(ser, "IDLE", 0, "--", "25", "25")
        time.sleep(3)
        for t in range(25, 216, 10):                       # heat up
            send(ser, "PRINTING", 0, "1h05", "%d/215" % t, "60/60")
            time.sleep(0.12)
        for p in range(0, 101, 2):                         # print
            send(ser, "PRINTING", p, fmt_eta((100 - p) * 60), "212/215", "60/60")
            time.sleep(0.4)
        send(ser, "DONE", 100, "--", "212", "60")
        time.sleep(6)
        send(ser, "PAUSED", 40, "--", "212/215", "60/60")
        time.sleep(4)


def main():
    ap = argparse.ArgumentParser(description="OctoPrint -> Matrix Portal sender")
    ap.add_argument("--url", default="http://octopi.local",
                    help="OctoPrint base URL (an IP address is most reliable on Windows)")
    ap.add_argument("--key", default="", help="OctoPrint application API key")
    ap.add_argument("--port", default=None, help="Matrix Portal COM port, e.g. COM7")
    ap.add_argument("--interval", type=float, default=2.0, help="poll seconds")
    ap.add_argument("--demo", action="store_true", help="send fake data, ignore OctoPrint")
    args = ap.parse_args()

    if not args.demo and not args.key:
        ap.error("--key is required (OctoPrint -> Settings -> Application Keys)")

    ser, last_snap = None, None
    while True:                                  # outer loop: reconnect forever
        if ser is None:
            dev = args.port or find_matrix_port()
            if dev is None:
                print("Matrix Portal not found (is code.py running?). Retrying...")
                time.sleep(3)
                continue
            try:
                ser = serial.Serial(dev, BAUD, timeout=1)
            except (serial.SerialException, OSError) as e:
                print("Cannot open %s: %s" % (dev, e))
                time.sleep(3)
                continue
            print("Connected to Matrix Portal on", dev)

        try:
            if args.demo:
                demo(ser)
            else:
                try:
                    snap = poll(args.url, args.key)
                except urllib.error.HTTPError as e:
                    print("OctoPrint HTTP %d (401 = bad API key?)" % e.code)
                    snap = ("OFFLINE", 0, "--", "--", "--")
                except (urllib.error.URLError, OSError, ValueError) as e:
                    print("OctoPrint unreachable:", e)
                    snap = ("OFFLINE", 0, "--", "--", "--")
                send(ser, *snap)
                if snap != last_snap:
                    print(time.strftime("%H:%M:%S") + "  " +
                          "%-8s %3d%%  ETA %-4s  N:%-8s B:%s" % snap)
                    last_snap = snap
                time.sleep(args.interval)
        except (serial.SerialException, OSError) as e:
            print("Serial lost, reconnecting:", e)
            try:
                ser.close()
            except Exception:
                pass
            ser = None
            time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nstopped")
