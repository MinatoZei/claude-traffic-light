"""
Claude Code Traffic Light — desktop-pet style widget.

A tiny always-on-top window styled like a traffic light:
  grey  = idle / Claude not running
  yellow (blinking) = running / processing
  red (blinking) = waiting for user confirmation
  green (blinking) = just finished (5s → idle)

Drag to move. Right-click to exit.
No dependencies beyond Python 3 + tkinter (bundled with Windows).
"""

import json
import os
import subprocess
import time
import tkinter as tk
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────

STATUS_DIR = Path(os.environ["USERPROFILE"]) / ".claude" / "traffic_status"
STATUS_FILE = Path(os.environ["USERPROFILE"]) / ".claude" / "traffic_status.json"  # legacy
SLOT_TTL = 30  # seconds before a stale slot is cleaned up
PRIORITY = {"needs_confirmation": 3, "running": 2, "finished": 1, "idle": 0}

POLL_MS = 500
FINISHED_TTL = 5  # seconds before "finished" → idle

# Bright / dim color pairs for each status
C = {
    "idle":               ("#555555", "#333333"),
    "running":            ("#ffcc00", "#665500"),
    "needs_confirmation": ("#ff1a1a", "#660000"),
    "finished":           ("#00cc44", "#004400"),
}
LABEL = {
    "idle":               "Idle",
    "running":            "Running",
    "needs_confirmation": "Confirm",
    "finished":           "Done!",
}

# Widget geometry
W = 56                # width
H = 188               # height
LIGHT_R = 18          # circle radius
LIGHT_Y = [36, 80, 124]  # y positions of red / yellow / green
LABEL_Y = 166         # status label y
BODY_LEFT, BODY_TOP, BODY_RIGHT, BODY_BOTTOM = 4, 4, W - 4, H - 4

# ── State ───────────────────────────────────────────────────────

_status = "idle"
_blink = False
_finished_at = 0.0
_session_count = 0
_win = None
_canvas = None
_circle_ids = {}
_label_id = None
_drag_x = _drag_y = 0

# ── Helpers ─────────────────────────────────────────────────────

def _claude_running():
    try:
        info = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq claude.exe"],
            capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return "claude.exe" in info.stdout
    except Exception:
        return False


def _read_status():
    global _finished_at, _session_count
    now = time.time()
    best_status = "idle"
    best_priority = 0
    active_slots = 0

    if STATUS_DIR.exists():
        for f in STATUS_DIR.glob("*.json"):
            if f.name.startswith("__"):
                continue
            try:
                raw = f.read_bytes()
                if raw.startswith(b"\xef\xbb\xbf"):
                    raw = raw[3:]
                data = json.loads(raw)
                status = data.get("status", "idle")
                ts = data.get("ts", 0)

                if now - ts > SLOT_TTL:
                    try:
                        f.unlink()
                    except Exception:
                        pass
                    continue

                active_slots += 1
                p = PRIORITY.get(status, 0)
                if p > best_priority:
                    best_priority = p
                    best_status = status
            except Exception:
                try:
                    f.unlink()
                except Exception:
                    pass

    _session_count = active_slots

    if best_status == "finished":
        if _finished_at == 0:
            _finished_at = now
        if now - _finished_at >= FINISHED_TTL:
            best_status = "idle"
            _finished_at = 0
    elif best_status == "idle":
        _finished_at = 0
    else:
        _finished_at = 0

    if not _claude_running():
        best_status = "idle"
        _finished_at = 0
        _session_count = 0

    return best_status


# ── Drawing ─────────────────────────────────────────────────────

def _draw_light(x, y, r, key):
    """Draw a single traffic light circle (outer ring + inner highlight)."""
    _, dim = C[key]
    _canvas.create_oval(x - r, y - r, x + r, y + r,
                        fill=dim, outline="#111111", width=1)
    hi_r = r - 6
    return _canvas.create_oval(x - hi_r, y - hi_r, x + hi_r, y + hi_r,
                               fill=dim, outline="")


def _draw_body():
    """Draw the rounded-rectangle black body."""
    r = 10  # corner radius
    x1, y1, x2, y2 = BODY_LEFT, BODY_TOP, BODY_RIGHT, BODY_BOTTOM
    # Use a series of shapes to simulate rounded rect
    _canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill="#1a1a1a", outline="")
    _canvas.create_rectangle(x1, y1 + r, x2, y2 - r, fill="#1a1a1a", outline="")
    _canvas.create_oval(x1, y1, x1 + 2 * r, y1 + 2 * r, fill="#1a1a1a", outline="")
    _canvas.create_oval(x2 - 2 * r, y1, x2, y1 + 2 * r, fill="#1a1a1a", outline="")
    _canvas.create_oval(x1, y2 - 2 * r, x1 + 2 * r, y2, fill="#1a1a1a", outline="")
    _canvas.create_oval(x2 - 2 * r, y2 - 2 * r, x2, y2, fill="#1a1a1a", outline="")


def _draw_all():
    """Full redraw of the widget."""
    global _label_id
    _canvas.delete("all")
    _draw_body()

    order = ["needs_confirmation", "running", "finished"]
    cx = W // 2
    for key, cy in zip(order, LIGHT_Y):
        _circle_ids[key] = _draw_light(cx, cy, LIGHT_R, key)

    _label_id = _canvas.create_text(W // 2, LABEL_Y,
                                    text=LABEL.get(_status, ""),
                                    fill="#777777", font=("Segoe UI", 8))


# ── Window management ───────────────────────────────────────────

def _start_drag(event):
    global _drag_x, _drag_y
    _drag_x, _drag_y = event.x, event.y


def _do_drag(event):
    if _win:
        x = _win.winfo_x() + (event.x - _drag_x)
        y = _win.winfo_y() + (event.y - _drag_y)
        _win.geometry(f"+{x}+{y}")


def _exit_app():
    global _win
    if _win:
        _win.destroy()
        _win = None


def _show_menu(event):
    menu = tk.Menu(_win, tearoff=0, bg="#2a2a2a", fg="#cccccc",
                   activebackground="#444444", activeforeground="#ffffff")
    menu.add_command(label="Exit", command=_exit_app)
    menu.post(event.x_root, event.y_root)


# ── Poll loop ───────────────────────────────────────────────────

def _poll():
    global _status, _blink
    _status = _read_status()
    _blink = not _blink

    # Update circle colours
    for key, cid in _circle_ids.items():
        bright, dim = C[key]
        if key == _status:
            color = bright if _blink else dim
        else:
            color = dim
        # Update the inner highlight circle
        _canvas.itemconfig(cid, fill=color)

    # Update label
    label_text = LABEL.get(_status, "")
    if _session_count > 1:
        label_text = f"{label_text} ({_session_count})"
    _canvas.itemconfig(_label_id, text=label_text)

    _win.after(POLL_MS, _poll)


# ── Entry point ─────────────────────────────────────────────────

def main():
    global _win, _canvas

    _win = tk.Tk()
    _win.title("Claude Traffic Light")

    # Window: no borders, always on top
    _win.overrideredirect(True)
    _win.attributes("-topmost", True)
    _win.resizable(False, False)
    _win.configure(bg="#1a1a1a")

    # Canvas with solid dark background
    _canvas = tk.Canvas(_win, width=W, height=H,
                        bg="#1a1a1a", highlightthickness=0)
    _canvas.pack()

    # Bindings
    _canvas.bind("<Button-1>", _start_drag)
    _canvas.bind("<B1-Motion>", _do_drag)
    _canvas.bind("<Button-3>", _show_menu)

    # Initial draw
    _draw_all()

    # Position: right side of screen, vertically centered
    sw = _win.winfo_screenwidth()
    sh = _win.winfo_screenheight()
    _win.geometry(f"+{sw - W - 20}+{(sh - H) // 2}")

    # Start poll
    _status = _read_status()
    _win.after(POLL_MS, _poll)

    # Ensure window shows on top
    _win.lift()
    _win.attributes("-topmost", True)

    _win.mainloop()


if __name__ == "__main__":
    main()
