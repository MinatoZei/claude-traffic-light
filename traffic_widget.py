#!/usr/bin/env python3
"""Claude Code desktop status widget (frameless, always-on-top).

Layout (mirrors the Codex-style panel):

    Claude limits
    5h left 90%                         3h17m
    [██████████░]                              <- fill = remaining %, red when low
    weekly left 85%                     4d22h
    [████████░░░]
    ● 后端                              5s
      opus-4-8 · 232M tok
    ● RuoYi-Vue3·a465                   12s
      opus-4-8 · 26M tok

Data:
  * per-session rows  -> ~/.claude/traffic_status/<session_id>.json written by
    traffic_hook.py  {status, ts, project, named, sid, model, tokens}
  * 5h / weekly bars  -> ~/.claude/traffic_status/ratelimits.json written by the
    statusline wrapper (install.py --with-limits). Real Anthropic numbers, only
    present for Pro/Max subscribers. If absent, the limits block is simply hidden
    (never a fake bar).

Runs Windows-side (real HWND_TOPMOST) reading via the \\wsl.localhost UNC path;
can also run inside WSL for debugging.

Forked from weilizhe8-del/claude-code-traffic-light (MIT).
"""
import os
import sys
import json
import time
import tkinter as tk

_DEFAULT_WIN_DIR = r"\\wsl.localhost\Ubuntu\root\.claude\traffic_status"
if os.environ.get("CLAUDE_TRAFFIC_DIR"):
    STATUS_DIR = os.environ["CLAUDE_TRAFFIC_DIR"]
elif sys.platform == "win32":
    STATUS_DIR = _DEFAULT_WIN_DIR
else:
    STATUS_DIR = os.path.expanduser("~/.claude/traffic_status")

POS_FILE = os.path.join(STATUS_DIR, "__widget_pos")
LIMITS_FILE = os.path.join(STATUS_DIR, "ratelimits.json")

# ---- tunables ---------------------------------------------------------------
DATA_POLL_MS = 2000
AGE_TICK_MS = 1000
DEAD_TTL = 6 * 3600
STALE = 30 * 60
NAME_MAX = 26
WIDTH = 280

BG = "#0f1012"
FG = "#e8eaed"
FG_MUTED = "#8a9099"
FG_STALE = "#4b5563"
BAR_TRACK = "#333740"
DOT = {
    "running": "#3b82f6",
    "needs_confirmation": "#f59e0b",
    "finished": "#22c55e",
    "idle": "#22c55e",
}
ORDER = {"needs_confirmation": 0, "running": 1, "finished": 2, "idle": 3}
FONT_HEAD = ("Microsoft YaHei UI", 11, "bold")
FONT_LIM = ("Microsoft YaHei UI", 11, "bold")
FONT_TITLE = ("Microsoft YaHei UI", 12)
FONT_SUB = ("Microsoft YaHei UI", 9)


def format_age(secs):
    secs = max(0, int(secs))
    if secs < 60:
        return "%ds" % secs
    if secs < 3600:
        return "%dm" % (secs // 60)
    return "%dh" % (secs // 3600)


def format_tokens(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ""
    if n >= 1_000_000:
        return "%dM" % round(n / 1_000_000)
    if n >= 1_000:
        return "%dk" % round(n / 1_000)
    return str(n)


def format_reset(epoch):
    if not epoch:
        return ""
    d = int(epoch - time.time())
    if d <= 0:
        return "0m"
    if d >= 86400:
        return "%dd%dh" % (d // 86400, (d % 86400) // 3600)
    if d >= 3600:
        return "%dh%dm" % (d // 3600, (d % 3600) // 60)
    return "%dm" % (d // 60)


def short_model(m):
    m = m or ""
    if m.startswith("claude-"):
        m = m[len("claude-"):]
    return m


def bar_color(remaining):
    if remaining < 12:
        return "#ef4444"   # red
    if remaining < 35:
        return "#f59e0b"   # orange
    return "#22c55e"       # green


def load_slots():
    rows, now = [], time.time()
    if not os.path.isdir(STATUS_DIR):
        return rows
    try:
        names = os.listdir(STATUS_DIR)
    except OSError:
        return rows
    for n in names:
        if n.startswith("__") or not n.endswith(".json") or n == "ratelimits.json":
            continue
        p = os.path.join(STATUS_DIR, n)
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        if now - d.get("ts", 0) > DEAD_TTL:
            try:
                os.remove(p)
            except OSError:
                pass
            continue
        rows.append(d)
    rows.sort(key=lambda d: (ORDER.get(d.get("status"), 9), -d.get("ts", 0)))
    return rows


def load_limits():
    try:
        with open(LIMITS_FILE, "r", encoding="utf-8") as f:
            lim = json.load(f)
    except Exception:
        return None
    if lim.get("five_used") is None and lim.get("week_used") is None:
        return None
    return lim


class Widget:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-alpha", 0.95)
        except tk.TclError:
            pass
        self.root.configure(bg=BG)

        self.blink_on = False
        self.fingerprint = None
        self.slots = {}
        self.row_widgets = {}
        self.reset_labels = []   # [(label, epoch)] countdowns updated each tick

        # invisible spacer pins a minimum window width even with short content
        tk.Frame(self.root, bg=BG, width=WIDTH, height=1).pack()
        self.head = tk.Label(self.root, text="Claude Code", font=FONT_HEAD,
                             fg=FG, bg=BG, anchor="w", padx=12, pady=5)
        self.head.pack(fill="x")
        self.body = tk.Frame(self.root, bg=BG)
        self.body.pack(fill="both", expand=True)

        for w in (self.root, self.head):
            self._bind_drag(w)
        self.root.bind("<Button-3>", lambda e: self.root.destroy())

        self._restore_pos()
        self.data_poll()
        self.age_tick()
        self.root.mainloop()

    # ---- dragging ----
    def _bind_drag(self, w):
        w.bind("<Button-1>", self._press)
        w.bind("<B1-Motion>", self._move)
        w.bind("<ButtonRelease-1>", lambda e: self._save_pos())

    def _press(self, e):
        self._dx, self._dy = e.x, e.y

    def _move(self, e):
        self.root.geometry("+%d+%d" % (self.root.winfo_pointerx() - self._dx,
                                       self.root.winfo_pointery() - self._dy))

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

    # ---- data poll ----
    def data_poll(self):
        slots = load_slots()
        lim = load_limits()
        self.slots = {s.get("sid", ""): s for s in slots}
        lim_fp = ((round(lim.get("five_used") or -1),
                   round(lim.get("week_used") or -1)) if lim else None)
        slot_fp = tuple((s.get("sid"), s.get("status"), s.get("project"),
                         s.get("named"), s.get("model"), s.get("tokens"))
                        for s in slots)
        fp = (lim_fp, slot_fp)
        if fp != self.fingerprint:
            self.fingerprint = fp
            self._rebuild(slots, lim)
        self.root.after(DATA_POLL_MS, self.data_poll)

    def _rebuild(self, slots, lim):
        for child in self.body.winfo_children():
            child.destroy()
        self.row_widgets = {}
        self.reset_labels = []
        self.head.config(text="Claude limits" if lim else "Claude Code")

        if lim:
            self._build_limits(lim)
            tk.Frame(self.body, bg=BAR_TRACK, height=1).pack(fill="x", padx=12, pady=(4, 2))

        if not slots:
            tk.Label(self.body, text="无活动会话", font=FONT_SUB,
                     fg=FG_MUTED, bg=BG, anchor="w", padx=12, pady=6).pack(anchor="w")
        for s in slots:
            self._build_row(s)
        self._refresh_dynamic()

    def _build_limits(self, lim):
        bw = WIDTH - 24
        for used_key, reset_key, title in (("five_used", "five_reset", "5h"),
                                           ("week_used", "week_reset", "weekly")):
            used = lim.get(used_key)
            if used is None:
                continue
            remaining = max(0, 100 - used)
            head = tk.Frame(self.body, bg=BG)
            head.pack(fill="x", padx=12, pady=(4, 0))
            tk.Label(head, text="%s left %d%%" % (title, round(remaining)),
                     font=FONT_LIM, fg=FG, bg=BG).pack(side="left")
            rl = tk.Label(head, text=format_reset(lim.get(reset_key)),
                          font=FONT_SUB, fg=FG_MUTED, bg=BG)
            rl.pack(side="right")
            self.reset_labels.append((rl, lim.get(reset_key)))

            bar = tk.Canvas(self.body, height=6, width=bw, bg=BG, highlightthickness=0)
            bar.pack(fill="x", padx=12, pady=(2, 2))
            bar.create_rectangle(0, 0, bw, 6, fill=BAR_TRACK, outline="")
            fillw = int(bw * remaining / 100.0)
            if fillw > 0:
                bar.create_rectangle(0, 0, fillw, 6, fill=bar_color(remaining), outline="")

    def _build_row(self, s):
        sid = s.get("sid", "")
        status = s.get("status") or ""
        row = tk.Frame(self.body, bg=BG)
        row.pack(fill="x", padx=10, pady=3)
        row.columnconfigure(1, weight=1)

        dot = tk.Canvas(row, width=12, height=12, bg=BG, highlightthickness=0)
        did = dot.create_oval(1, 1, 11, 11, fill=DOT.get(status, FG_MUTED), outline="")
        dot.grid(row=0, column=0, rowspan=2, padx=(2, 9))

        proj = s.get("project") or "?"
        if len(proj) > NAME_MAX:
            proj = proj[:NAME_MAX - 1] + "…"
        title = proj if s.get("named") else "%s·%s" % (proj, (sid or "")[:6])
        tl = tk.Label(row, text=title, font=FONT_TITLE, fg=FG, bg=BG, anchor="w")
        tl.grid(row=0, column=1, sticky="w")

        parts = [short_model(s.get("model") or "")]
        if s.get("tokens"):
            parts.append(format_tokens(s.get("tokens")) + " tok")
        sub = " · ".join(p for p in parts if p) or "—"
        sl = tk.Label(row, text=sub, font=FONT_SUB, fg=FG_MUTED, bg=BG, anchor="w")
        sl.grid(row=1, column=1, sticky="w")

        al = tk.Label(row, text="", font=FONT_SUB, fg=FG_MUTED, bg=BG)
        al.grid(row=0, column=2, rowspan=2, sticky="e", padx=(6, 4))

        self.row_widgets[sid] = {"dot": dot, "dot_id": did, "title": tl, "age": al}

    # ---- age tick (in memory) ----
    def age_tick(self):
        self.blink_on = not self.blink_on
        self._refresh_dynamic()
        self.root.after(AGE_TICK_MS, self.age_tick)

    def _refresh_dynamic(self):
        now = time.time()
        for lbl, epoch in self.reset_labels:
            lbl.config(text=format_reset(epoch))
        for sid, w in self.row_widgets.items():
            s = self.slots.get(sid)
            if not s:
                continue
            status = s.get("status")
            age = now - s.get("ts", now)
            w["age"].config(text=format_age(age))
            stale = (status == "running" and age > STALE)
            w["title"].config(fg=FG_STALE if stale else FG)
            if status == "needs_confirmation":
                color = DOT["needs_confirmation"] if self.blink_on else BG
            else:
                color = DOT.get(status, FG_MUTED)
            w["dot"].itemconfig(w["dot_id"], fill=color)


if __name__ == "__main__":
    Widget()
