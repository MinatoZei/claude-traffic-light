#!/usr/bin/env python3
"""Claude Code desktop status widget (frameless, always-on-top).

Lists every active Claude Code session as one row:
    <dot>  project·shortid        <status>        <age>
Data comes from the per-session JSON files written by traffic_hook.py.

Runs on the WINDOWS side (Python + tkinter) so `-topmost` maps to a real
HWND_TOPMOST and stays above native Windows windows. It reads the status files
that Claude Code (running in WSL) writes, via the \\wsl.localhost UNC path.
Can also run inside WSL for debugging (reads ~/.claude/traffic_status).

Forked from weilizhe8-del/claude-code-traffic-light (MIT). The window skeleton
(overrideredirect + -topmost + after() poll + drag + right-click quit) follows
the original; the single aggregate light is replaced by a per-session list with
"time since last activity", incremental redraw and position memory.
"""
import os
import sys
import json
import time
import tkinter as tk

# ---- where the per-session status files live --------------------------------
# Override with the CLAUDE_TRAFFIC_DIR env var if your distro/user differs.
_DEFAULT_WIN_DIR = r"\\wsl.localhost\Ubuntu\root\.claude\traffic_status"
if os.environ.get("CLAUDE_TRAFFIC_DIR"):
    STATUS_DIR = os.environ["CLAUDE_TRAFFIC_DIR"]
elif sys.platform == "win32":
    STATUS_DIR = _DEFAULT_WIN_DIR
else:
    STATUS_DIR = os.path.expanduser("~/.claude/traffic_status")

POS_FILE = os.path.join(STATUS_DIR, "__widget_pos")

# ---- tunables (all here on purpose; tweak freely) ---------------------------
DATA_POLL_MS = 2000     # how often we actually hit the disk / 9P bridge
AGE_TICK_MS = 1000      # in-memory only: bump age text + blink, no disk read
DEAD_TTL = 6 * 3600     # drop a slot not updated in 6h (zombie session)
STALE = 30 * 60         # a "running" slot older than this is greyed (maybe dead)
WIDTH = 250

BG = "#111214"
FG = "#e5e7eb"
FG_MUTED = "#9ca3af"
FG_STALE = "#4b5563"
COLORS = {
    "running": "#3b82f6",
    "needs_confirmation": "#f59e0b",
    "finished": "#22c55e",
    "idle": "#6b7280",
}
LABEL = {
    "running": "运行中",
    "needs_confirmation": "待确认",
    "finished": "已完成",
    "idle": "空闲",
}
ORDER = {"needs_confirmation": 0, "running": 1, "finished": 2, "idle": 3}
FONT = ("Microsoft YaHei UI", 10)
FONT_HEAD = ("Microsoft YaHei UI", 10, "bold")


def format_age(secs):
    secs = max(0, int(secs))
    if secs < 60:
        return "%ds" % secs
    if secs < 3600:
        return "%dm" % (secs // 60)
    return "%dh" % (secs // 3600)


def load_slots():
    """Read all session slot files, drop zombies, return sorted list of dicts."""
    rows = []
    now = time.time()
    if not os.path.isdir(STATUS_DIR):
        return rows
    try:
        names = os.listdir(STATUS_DIR)
    except OSError:
        return rows
    for n in names:
        if n.startswith("__") or not n.endswith(".json"):
            continue
        p = os.path.join(STATUS_DIR, n)
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue  # half-written / corrupt; try again next poll
        ts = d.get("ts", 0)
        if now - ts > DEAD_TTL:
            try:
                os.remove(p)
            except OSError:
                pass
            continue
        rows.append(d)
    rows.sort(key=lambda d: (ORDER.get(d.get("status"), 9), -d.get("ts", 0)))
    return rows


class Widget:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-alpha", 0.94)
        except tk.TclError:
            pass
        self.root.configure(bg=BG)

        self.blink_on = False
        self.fingerprint = None
        self.slots = {}          # sid -> slot dict (kept fresh every data poll)
        self.row_widgets = {}    # sid -> {dot, dot_id, name_lbl, status_lbl, age_lbl}

        head = tk.Label(self.root, text="Claude Code", font=FONT_HEAD,
                        fg=FG, bg=BG, anchor="w", padx=10, pady=4)
        head.pack(fill="x")
        self.body = tk.Frame(self.root, bg=BG)
        self.body.pack(fill="both", expand=True)
        self.body.columnconfigure(1, weight=1)

        for w in (self.root, head):
            self._bind_drag(w)
        self.root.bind("<Button-3>", lambda e: self.root.destroy())

        self._restore_pos()
        self.data_poll()
        self.age_tick()
        self.root.mainloop()

    # ---- dragging ----------------------------------------------------------
    def _bind_drag(self, w):
        w.bind("<Button-1>", self._press)
        w.bind("<B1-Motion>", self._move)
        w.bind("<ButtonRelease-1>", lambda e: self._save_pos())

    def _press(self, e):
        self._dx, self._dy = e.x, e.y

    def _move(self, e):
        x = self.root.winfo_pointerx() - self._dx
        y = self.root.winfo_pointery() - self._dy
        self.root.geometry("+%d+%d" % (x, y))

    def _restore_pos(self):
        pos = "+80+80"
        try:
            with open(POS_FILE, "r") as f:
                saved = f.read().strip()
            if saved.startswith("+"):
                pos = saved
        except Exception:
            pass
        self.root.geometry(pos)

    def _save_pos(self):
        try:
            with open(POS_FILE, "w") as f:
                f.write("+%d+%d" % (self.root.winfo_x(), self.root.winfo_y()))
        except OSError:
            pass

    # ---- data poll (touches disk) -----------------------------------------
    def data_poll(self):
        slots = load_slots()
        self.slots = {s.get("sid", ""): s for s in slots}
        fp = tuple((s.get("sid"), s.get("status")) for s in slots)
        if fp != self.fingerprint:
            self.fingerprint = fp
            self._rebuild(slots)
        self.root.after(DATA_POLL_MS, self.data_poll)

    def _rebuild(self, slots):
        for child in self.body.winfo_children():
            child.destroy()
        self.row_widgets = {}

        if not slots:
            tk.Label(self.body, text="无活动会话", font=FONT,
                     fg=FG_MUTED, bg=BG, anchor="w", padx=10, pady=6).grid(
                row=0, column=0, columnspan=4, sticky="w")
            self._resize(0)
            return

        for r, s in enumerate(slots):
            sid = s.get("sid", "")
            status = s.get("status") or ""
            dot = tk.Canvas(self.body, width=12, height=12, bg=BG,
                            highlightthickness=0)
            dot_id = dot.create_oval(2, 2, 11, 11,
                                     fill=COLORS.get(status, FG_MUTED),
                                     outline="")
            dot.grid(row=r, column=0, padx=(10, 6), pady=2)

            name = "%s·%s" % (s.get("project", "?"), (sid or "")[:6])
            name_lbl = tk.Label(self.body, text=name, font=FONT, fg=FG, bg=BG,
                                anchor="w")
            name_lbl.grid(row=r, column=1, sticky="w")

            status_lbl = tk.Label(self.body, text=LABEL.get(status, status),
                                  font=FONT, fg=FG, bg=BG)
            status_lbl.grid(row=r, column=2, padx=6)

            age_lbl = tk.Label(self.body, text="", font=FONT, fg=FG_MUTED, bg=BG,
                               anchor="e", width=4)
            age_lbl.grid(row=r, column=3, sticky="e", padx=(0, 10))

            self.row_widgets[sid] = {
                "dot": dot, "dot_id": dot_id, "name_lbl": name_lbl,
                "status_lbl": status_lbl, "age_lbl": age_lbl,
            }
        self._resize(len(slots))
        self._refresh_dynamic()  # fill ages immediately, no 1s wait

    def _resize(self, n):
        h = 26 + max(1, n) * 22 + 8
        self.root.geometry("%dx%d" % (WIDTH, h))

    # ---- age tick (in memory only) ----------------------------------------
    def age_tick(self):
        self.blink_on = not self.blink_on
        self._refresh_dynamic()
        self.root.after(AGE_TICK_MS, self.age_tick)

    def _refresh_dynamic(self):
        now = time.time()
        for sid, w in self.row_widgets.items():
            s = self.slots.get(sid)
            if not s:
                continue
            status = s.get("status")
            age = now - s.get("ts", now)
            w["age_lbl"].config(text=format_age(age))

            stale = (status == "running" and age > STALE)
            fg = FG_STALE if stale else FG
            w["name_lbl"].config(fg=fg)
            w["status_lbl"].config(fg=fg)

            # only "needs_confirmation" blinks; everything else is steady
            if status == "needs_confirmation":
                color = COLORS["needs_confirmation"] if self.blink_on else BG
            else:
                color = COLORS.get(status, FG_MUTED)
            w["dot"].itemconfig(w["dot_id"], fill=color)


if __name__ == "__main__":
    Widget()
