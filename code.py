# code.py -- OctoPrint status display for Matrix Portal M4 + 32x64 RGB matrix
#
# ONE fixed screen:
#   y =  0.. 6 : "45% 1h05" while printing, otherwise the state word
#   y =  9..15 : nozzle temperature
#   y = 18..24 : bed temperature
#   y =    25  : one blank pixel (margin)
#   y = 26..31 : progress bar
#
# Text is drawn pixel-by-pixel from a 5x7 font defined INSIDE this file.
# No .bdf files, no font libraries, no firmware internals: character i is
# always at x = i*6, every line always starts at x = 0. Cannot drift.
#
# DIAGNOSTICS: any crash, anywhere, is printed to serial, written to
# /error.txt on CIRCUITPY (open it in Mu), and shown as CRASH on the matrix.
# error.txt is deleted again on a clean start.
#
# Serial protocol (unchanged, see octoprint_to_matrix.py):
#   S=<state>  P=<percent>  E=<eta>  N=<nozzle>  B=<bed>   PING -> PONG

import os
import sys
import time

# ----------------------------- tweakables ---------------------------------
BIT_DEPTH    = 4      # 2..4: lower if it flickers, higher for smoother colors
BRIGHTNESS   = 0.4    # 1.0 = full brightness as before; every color is
                      # multiplied by this per R/G/B channel (0.3 = night dim)
HOST_TIMEOUT = 10.0   # seconds of serial silence before showing NOHOST

GLYPH_W, GLYPH_H, ADVANCE = 5, 7, 6     # 5 px wide + 1 px gap per character
MAX_CHARS = 64 // ADVANCE               # 10 characters fit on a line
ROW_YS = (0, 9, 18)                     # top pixel of each text line
BAR_Y, BAR_H = 26, 6                    # progress bar: 1 px margin above,
                                        # flush with the bottom edge

STATE_COLORS = {
    "PRINTING": 0x00FF00,   # green
    "PAUSED":   0xFFC000,   # amber
    "DONE":     0x00FFFF,   # cyan
    "IDLE":     0xC0C0C0,   # dim white
    "STOPPED":  0xFF8000,   # orange
    "ERROR":    0xFF0000,   # red
    "OFFLINE":  0x606060,   # gray: OctoPrint unreachable / printer unplugged
    "NOHOST":   0x606060,   # gray: no serial data from the sender
    "WAITING":  0x404040,   # dark gray: just booted
}
NOZZLE_COLOR  = 0xFF8000
BED_COLOR     = 0x0080FF
BAR_TRACK     = 0x101010   # empty part of the progress bar
UNKNOWN_COLOR = 0xFF00FF   # magenta: unrecognized state string

# ----------------------------- dimming ------------------------------------
def dim(color):
    """Multiply a 0xRRGGBB color by BRIGHTNESS, one channel at a time."""
    r = int(((color >> 16) & 0xFF) * BRIGHTNESS)
    g = int(((color >> 8) & 0xFF) * BRIGHTNESS)
    b = int((color & 0xFF) * BRIGHTNESS)
    return (r << 16) | (g << 8) | b

# ----------------------------- the 5x7 font -------------------------------
# Each glyph = 7 numbers, one per pixel row, 5 bits each, leftmost pixel =
# highest bit. Read them top to bottom and you can literally see the letter.
# Unknown characters render blank; unknown lowercase falls back to uppercase.
FONT = {
    " ": (0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000),
    "!": (0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00000, 0b00100),
    "%": (0b11000, 0b11001, 0b00010, 0b00100, 0b01000, 0b10011, 0b00011),
    "+": (0b00000, 0b00100, 0b00100, 0b11111, 0b00100, 0b00100, 0b00000),
    "-": (0b00000, 0b00000, 0b00000, 0b01110, 0b00000, 0b00000, 0b00000),
    ".": (0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00110, 0b00110),
    "/": (0b00001, 0b00010, 0b00100, 0b00100, 0b01000, 0b01000, 0b10000),
    ":": (0b00000, 0b00000, 0b00100, 0b00000, 0b00000, 0b00100, 0b00000),
    "0": (0b01110, 0b10001, 0b10011, 0b10101, 0b11001, 0b10001, 0b01110),
    "1": (0b00100, 0b01100, 0b00100, 0b00100, 0b00100, 0b00100, 0b01110),
    "2": (0b01110, 0b10001, 0b00001, 0b00010, 0b00100, 0b01000, 0b11111),
    "3": (0b01110, 0b10001, 0b00001, 0b00110, 0b00001, 0b10001, 0b01110),
    "4": (0b00010, 0b00110, 0b01010, 0b10010, 0b11111, 0b00010, 0b00010),
    "5": (0b11111, 0b10000, 0b11110, 0b00001, 0b00001, 0b10001, 0b01110),
    "6": (0b00110, 0b01000, 0b10000, 0b11110, 0b10001, 0b10001, 0b01110),
    "7": (0b11111, 0b00001, 0b00010, 0b00100, 0b01000, 0b01000, 0b01000),
    "8": (0b01110, 0b10001, 0b10001, 0b01110, 0b10001, 0b10001, 0b01110),
    "9": (0b01110, 0b10001, 0b10001, 0b01111, 0b00001, 0b00010, 0b01100),
    "A": (0b01110, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001),
    "B": (0b11110, 0b10001, 0b10001, 0b11110, 0b10001, 0b10001, 0b11110),
    "C": (0b01110, 0b10001, 0b10000, 0b10000, 0b10000, 0b10001, 0b01110),
    "D": (0b11110, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b11110),
    "E": (0b11111, 0b10000, 0b10000, 0b11110, 0b10000, 0b10000, 0b11111),
    "F": (0b11111, 0b10000, 0b10000, 0b11110, 0b10000, 0b10000, 0b10000),
    "G": (0b01110, 0b10001, 0b10000, 0b10111, 0b10001, 0b10001, 0b01110),
    "H": (0b10001, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001),
    "I": (0b01110, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b01110),
    "J": (0b00010, 0b00010, 0b00010, 0b00010, 0b00010, 0b10010, 0b01100),
    "K": (0b10001, 0b10010, 0b10100, 0b11000, 0b10100, 0b10010, 0b10001),
    "L": (0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b11111),
    "M": (0b10001, 0b11011, 0b10101, 0b10101, 0b10001, 0b10001, 0b10001),
    "N": (0b10001, 0b11001, 0b10101, 0b10011, 0b10001, 0b10001, 0b10001),
    "O": (0b01110, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110),
    "P": (0b11110, 0b10001, 0b10001, 0b11110, 0b10000, 0b10000, 0b10000),
    "Q": (0b01110, 0b10001, 0b10001, 0b10001, 0b10001, 0b10101, 0b01101),
    "R": (0b11110, 0b10001, 0b10001, 0b11110, 0b10100, 0b10010, 0b10001),
    "S": (0b01111, 0b10000, 0b10000, 0b01110, 0b00001, 0b00001, 0b11110),
    "T": (0b11111, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100),
    "U": (0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110),
    "V": (0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01010, 0b00100),
    "W": (0b10001, 0b10001, 0b10001, 0b10101, 0b10101, 0b10101, 0b01010),
    "X": (0b10001, 0b10001, 0b01010, 0b00100, 0b01010, 0b10001, 0b10001),
    "Y": (0b10001, 0b10001, 0b01010, 0b00100, 0b00100, 0b00100, 0b00100),
    "Z": (0b11111, 0b00001, 0b00010, 0b00100, 0b01000, 0b10000, 0b11111),
    "h": (0b10000, 0b10000, 0b11110, 0b10001, 0b10001, 0b10001, 0b10001),
    "m": (0b00000, 0b00000, 0b11011, 0b10101, 0b10101, 0b10101, 0b10101),
}


# --------------------------- crash reporter --------------------------------
def fatal(exc):
    """Report exc to serial, to /error.txt and to the matrix, then halt."""
    try:
        sys.print_exception(exc)                    # -> serial console
    except Exception:
        pass
    text = None
    try:
        import io
        buf = io.StringIO()
        sys.print_exception(exc, buf)               # -> string
        text = buf.getvalue()
    except Exception:
        pass
    try:
        with open("/error.txt", "w") as f:
            f.write("code.py stopped with this error.\n")
            f.write("(Deleted again on a successful start, so if you can\n")
            f.write(" read this now, it is the current error.)\n\n")
            try:
                u = os.uname()
                f.write("CircuitPython %s on %s\n\n" % (u.release, u.machine))
            except Exception:
                pass
            f.write(text if text else (repr(exc) + "\n"))
    except Exception:
        pass
    try:                                            # -> matrix, if it is up
        rs = globals().get("row_state")
        if rs is not None:
            rs.set_color(0xFF0000)
            rs.set_text("CRASH")
        rn = globals().get("row_nozzle")
        if rn is not None:
            rn.set_text(str(exc)[:MAX_CHARS])
        rb = globals().get("row_bed")
        if rb is not None:
            rb.set_text("err.txt")
    except Exception:
        pass
    while True:                                     # keep the REPL reachable
        time.sleep(1)


# ============== everything below can now fail safely =======================
try:
    import board
    import displayio
    import framebufferio
    import rgbmatrix
    import usb_cdc

    # ----------------------------- matrix display --------------------------
    displayio.release_displays()

    def _pin(*names):
        """First pin that exists on this board (names vary by CP version)."""
        for name in names:
            if hasattr(board, name):
                return getattr(board, name)
        raise AttributeError("This board has none of these pins: "
                             + ", ".join(names))

    matrix = rgbmatrix.RGBMatrix(
        width=64, height=32, bit_depth=BIT_DEPTH,
        rgb_pins=[_pin("MTX_R1"), _pin("MTX_G1"), _pin("MTX_B1"),
                  _pin("MTX_R2"), _pin("MTX_G2"), _pin("MTX_B2")],
        addr_pins=[_pin("MTX_ADDRA"), _pin("MTX_ADDRB"),
                   _pin("MTX_ADDRC"), _pin("MTX_ADDRD")],
        clock_pin=_pin("MTX_CLK"),
        latch_pin=_pin("MTX_LAT", "MTX_LATCH"),
        output_enable_pin=_pin("MTX_OE"),
    )
    display = framebufferio.FramebufferDisplay(matrix, auto_refresh=True)

    # ------------------------------ text rows ------------------------------
    class TextRow:
        """One text line on a fixed pixel row, always flush left."""

        def __init__(self, y, color):
            self.palette = displayio.Palette(2)
            self.palette[0] = 0x000000      # background
            self.palette[1] = dim(color)    # ink
            self.bitmap = displayio.Bitmap(64, 8, 2)
            self.tile = displayio.TileGrid(self.bitmap,
                                           pixel_shader=self.palette)
            self.tile.x = 0                 # left edge, always
            self.tile.y = y
            self._last = None
            self.set_text("")

        def set_text(self, text):
            text = str(text)[:MAX_CHARS]
            if text == self._last:
                return
            self._last = text
            bm = self.bitmap
            bm.fill(0)
            for i, ch in enumerate(text):
                glyph = (FONT.get(ch) or FONT.get(ch.upper())
                         or FONT.get(ch.lower()))
                if glyph is None:
                    continue                # unknown char -> blank cell
                x0 = i * ADVANCE
                for r in range(GLYPH_H):
                    bits = glyph[r]
                    if not bits:
                        continue
                    for c in range(GLYPH_W):
                        if bits & (0x10 >> c):
                            bm[x0 + c, r] = 1

        def set_color(self, color):
            self.palette[1] = dim(color)

    row_state  = TextRow(ROW_YS[0], STATE_COLORS["WAITING"])
    row_nozzle = TextRow(ROW_YS[1], NOZZLE_COLOR)
    row_bed    = TextRow(ROW_YS[2], BED_COLOR)

    # ----------------------------- progress bar ----------------------------
    bar_bitmap  = displayio.Bitmap(64, BAR_H, 2)
    bar_palette = displayio.Palette(2)
    bar_palette[0] = BAR_TRACK      # already near-black: NOT dimmed further
    bar_palette[1] = dim(0x00FF00)
    bar = displayio.TileGrid(bar_bitmap, pixel_shader=bar_palette)
    bar.x, bar.y = 0, BAR_Y

    root = displayio.Group()
    for item in (row_state.tile, row_nozzle.tile, row_bed.tile, bar):
        root.append(item)
    try:
        display.root_group = root           # CircuitPython 8+
    except AttributeError:
        display.show(root)                  # older versions

    # ----------------------------- serial ports ----------------------------
    ports = []
    try:
        if usb_cdc.console is not None:
            ports.append(usb_cdc.console)
        if usb_cdc.data is not None:
            ports.append(usb_cdc.data)
    except AttributeError:
        pass
    acc = ["" for _ in ports]

    # ----------------------------- state + drawing -------------------------
    state, pct, eta = "WAITING", 0, "--"
    bar_drawn = None

    def state_color(st):
        return STATE_COLORS.get(st, UNKNOWN_COLOR)

    def draw_state_row():
        if state == "PRINTING":
            text = "%d%% %s" % (min(pct, 99), eta)
        else:
            text = state
        row_state.set_text(text)
        row_state.set_color(state_color(state))

    def draw_bar():
        global bar_drawn
        fill = int(round(max(0, min(100, pct)) * 64 / 100))
        color = state_color(state)
        if bar_drawn == (fill, color):
            return
        bar_drawn = (fill, color)
        bar_palette[1] = dim(color)
        for x in range(64):
            v = 1 if x < fill else 0
            for y in range(BAR_H):
                bar_bitmap[x, y] = v

    def set_temps(trow, prefix, val):
        if not val:
            val = "--"
        trow.set_text((prefix + val)[:MAX_CHARS])

    def set_state(new):
        global state
        new = new.strip().upper()[:MAX_CHARS]
        if new and new != state:
            state = new
            draw_state_row()
            draw_bar()

    def handle_line(line, port):
        global pct, eta
        line = line.strip()
        if not line:
            return
        if line.upper() == "PING":
            try:
                port.write(b"PONG\n")
            except Exception:
                pass
            return
        if "=" not in line:
            return
        key, _, val = line.partition("=")
        key = key.strip().upper()
        val = val.strip()
        if key == "S":
            set_state(val)
        elif key == "P":
            try:
                pct = int(float(val))
            except ValueError:
                pct = 0
            draw_bar()
            if state == "PRINTING":
                draw_state_row()
        elif key == "E":
            eta = val[:4] or "--"
            if state == "PRINTING":
                draw_state_row()
        elif key == "N":
            set_temps(row_nozzle, "N", val)
        elif key == "B":
            set_temps(row_bed, "B", val)

    # ----------------------------- main loop -------------------------------
    set_temps(row_nozzle, "N", "--")
    set_temps(row_bed, "B", "--")
    draw_state_row()
    draw_bar()

    try:            # first frame drawn OK -> remove any old error file
        os.remove("/error.txt")
    except OSError:
        pass

    last_rx = None          # None = no host heard from yet

    while True:
        for i, port in enumerate(ports):
            try:
                n = port.in_waiting
            except Exception:
                n = 0
            if n:
                try:
                    acc[i] += port.read(n).decode("ascii", "ignore")
                except Exception:
                    acc[i] = ""             # usb hiccup: drop partial line
                    continue
                while "\n" in acc[i]:
                    cmd, acc[i] = acc[i].split("\n", 1)
                    handle_line(cmd, port)
                    last_rx = time.monotonic()
                if len(acc[i]) > 128:      # junk without newlines
                    acc[i] = acc[i][-32:]

        if last_rx is not None and time.monotonic() - last_rx > HOST_TIMEOUT:
            if state != "NOHOST":
                pct = 0
                set_state("NOHOST")

        time.sleep(0.02)

except Exception as exc:
    fatal(exc)
