#!/usr/bin/env python3
"""Claude Code desktop status widget (frameless, always-on-top).

Layout (Codex-style panel):

    Claude limits                        ▾
    5h left 90%                       3h17m
    [██████████░]
    weekly left 85%                   4d22h
    [████████░░░]
    ● 后端                               5s
      运行中 · opus-4-8 · 232M tok
    ● RuoYi-Vue3·a465                   12s
      已完成 · opus-4-8 · 26M tok

Interactions:
  * drag anywhere on the header to move (position remembered)
  * double-click the header  -> collapse to a slim title bar / expand again
  * drag the bottom-right grip -> resize width freely
  * Ctrl + mouse wheel       -> scale the whole widget smaller / bigger
  * right-click              -> quit
  All of pos / width / scale / collapsed are persisted.

Data:
  * per-session rows  <- ~/.claude/traffic_status/<session_id>.json (traffic_hook.py)
  * 5h / weekly bars  <- ratelimits.json (statusline wrapper, Pro/Max only);
    hidden when absent — never a fake bar.

Runs Windows-side (real HWND_TOPMOST) reading via \\wsl.localhost UNC; can also
run inside WSL for debugging.

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

STATE_FILE = os.path.join(STATUS_DIR, "__widget_pos")
LIMITS_FILE = os.path.join(STATUS_DIR, "ratelimits.json")

# ---- tunables ---------------------------------------------------------------
DATA_POLL_MS = 2000
AGE_TICK_MS = 1000
DEAD_TTL = 6 * 3600
STALE = 30 * 60
NAME_MAX = 26
BASE_WIDTH = 280
MIN_WIDTH, MAX_WIDTH = 170, 640
MIN_SCALE, MAX_SCALE = 0.6, 1.6

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
LABEL = {
    "running": "运行中",
    "needs_confirmation": "待确认",
    "finished": "已完成",
    "idle": "空闲",
}
STATUS_FG = dict(DOT, idle=FG_MUTED)
ORDER = {"needs_confirmation": 0, "running": 1, "finished": 2, "idle": 3}
FAMILY = "Microsoft YaHei UI"


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
        return "#ef4444"
    if remaining < 35:
        return "#f59e0b"
    return "#22c55e"


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
        st = self._load_state()
        self.width = min(MAX_WIDTH, max(MIN_WIDTH, int(st.get("width", BASE_WIDTH))))
        self.scale = min(MAX_SCALE, max(MIN_SCALE, float(st.get("scale", 1.0))))
        self.collapsed = bool(st.get("collapsed", False))
        self._pos = st.get("pos", "+80+80")
        self._make_fonts()

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
        self.reset_labels = []

        # spacer pins the minimum window width (resize grip adjusts it)
        self.spacer = tk.Frame(self.root, bg=BG, width=self.width, height=1)
        self.spacer.pack()

        self.header = tk.Frame(self.root, bg=BG)
        self.header.pack(fill="x")
        self.head_lbl = tk.Label(self.header, text="Claude Code", font=self.f_head,
                                 fg=FG, bg=BG, anchor="w", padx=12, pady=5)
        self.head_lbl.pack(side="left")
        self.toggle_lbl = tk.Label(self.header, text="▸" if self.collapsed else "▾",
                                   font=self.f_sub, fg=FG_MUTED, bg=BG, padx=10)
        self.toggle_lbl.pack(side="right")

        self.body = tk.Frame(self.root, bg=BG)
        self.grip = tk.Canvas(self.root, width=14, height=14, bg=BG,
                              highlightthickness=0)
        for cur in ("size_nw_se", "bottom_right_corner", "sizing"):
            try:                       # cursor names differ per platform
                self.grip.configure(cursor=cur)
                break
            except tk.TclError:
                continue
        for off in (3, 7, 11):
            self.grip.create_line(off, 14, 14, off, fill=FG_MUTED)
        if not self.collapsed:
            self._show_body()

        for w in (self.root, self.header, self.head_lbl, self.toggle_lbl):
            self._bind_drag(w)
            w.bind("<Button-3>", lambda e: self.root.destroy())
        for w in (self.header, self.head_lbl, self.toggle_lbl):
            w.bind("<Double-Button-1>", self._toggle_collapse)
        self.grip.bind("<B1-Motion>", self._grip_drag)
        self.grip.bind("<ButtonRelease-1>", self._grip_release)
        self.root.bind_all("<Control-MouseWheel>", self._wheel)

        self.root.geometry(self._pos if self._pos.startswith("+") else "+80+80")
        self.data_poll()
        self.age_tick()
        self.root.mainloop()

    # ---- fonts / persisted state -------------------------------------------
    def _make_fonts(self):
        s = self.scale
        self.f_head = (FAMILY, max(7, round(11 * s)), "bold")
        self.f_lim = (FAMILY, max(7, round(11 * s)), "bold")
        self.f_title = (FAMILY, max(7, round(12 * s)))
        self.f_sub = (FAMILY, max(6, round(9 * s)))

    def _load_state(self):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                raw = f.read().strip()
        except Exception:
            return {}
        if raw.startswith("+"):          # legacy "+x+y" format
            return {"pos": raw}
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def _save_state(self):
        st = {"pos": "+%d+%d" % (self.root.winfo_x(), self.root.winfo_y()),
              "width": self.width, "scale": round(self.scale, 2),
              "collapsed": self.collapsed}
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(st, f)
        except OSError:
            pass

    # ---- move / collapse / resize / zoom ------------------------------------
    def _bind_drag(self, w):
        w.bind("<Button-1>", self._press)
        w.bind("<B1-Motion>", self._move)
        w.bind("<ButtonRelease-1>", lambda e: self._save_state())

    def _press(self, e):
        self._dx, self._dy = e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y()

    def _move(self, e):
        self.root.geometry("+%d+%d" % (e.x_root - self._dx, e.y_root - self._dy))

    def _show_body(self):
        self.grip.pack(side="bottom", anchor="e", padx=3, pady=2)
        self.body.pack(fill="both", expand=True)

    def _toggle_collapse(self, e=None):
        self.collapsed = not self.collapsed
        if self.collapsed:
            self.body.pack_forget()
            self.grip.pack_forget()
        else:
            self._show_body()
        self.toggle_lbl.config(text="▸" if self.collapsed else "▾")
        self._save_state()

    def _grip_drag(self, e):
        w = e.x_root - self.root.winfo_rootx()
        self.width = min(MAX_WIDTH, max(MIN_WIDTH, w))
        self.spacer.config(width=self.width)

    def _grip_release(self, e=None):
        self._save_state()
        self.fingerprint = None      # bar widths depend on width -> rebuild
        self._sync()

    def _wheel(self, e):
        step = 0.05 if getattr(e, "delta", 0) > 0 else -0.05
        self.scale = min(MAX_SCALE, max(MIN_SCALE, round(self.scale + step, 2)))
        self._make_fonts()
        self.head_lbl.config(font=self.f_head)
        self.toggle_lbl.config(font=self.f_sub)
        self._save_state()
        self.fingerprint = None
        self._sync()

    # ---- data ---------------------------------------------------------------
    def _sync(self):
        slots = load_slots()
        lim = load_limits()
        self.slots = {s.get("sid", ""): s for s in slots}
        lim_fp = ((round(lim.get("five_used") or -1),
                   round(lim.get("week_used") or -1)) if lim else None)
        slot_fp = tuple((s.get("sid"), s.get("status"), s.get("project"),
                         s.get("named"), s.get("model"), s.get("tokens"))
                        for s in slots)
        fp = (lim_fp, slot_fp, self.width, self.scale)
        if fp != self.fingerprint:
            self.fingerprint = fp
            self._rebuild(slots, lim)

    def data_poll(self):
        self._sync()
        self.root.after(DATA_POLL_MS, self.data_poll)

    # ---- rendering ----------------------------------------------------------
    def _rebuild(self, slots, lim):
        for child in self.body.winfo_children():
            child.destroy()
        self.row_widgets = {}
        self.reset_labels = []
        self.head_lbl.config(text="Claude limits" if lim else "Claude Code")

        if lim:
            self._build_limits(lim)
            tk.Frame(self.body, bg=BAR_TRACK, height=1).pack(fill="x", padx=12, pady=3)

        if not slots:
            tk.Label(self.body, text="无活动会话", font=self.f_sub,
                     fg=FG_MUTED, bg=BG, anchor="w", padx=12, pady=6).pack(anchor="w")
        for s in slots:
            self._build_row(s)
        self._refresh_dynamic()

    def _build_limits(self, lim):
        bw = max(60, self.width - 24)
        for used_key, reset_key, title in (("five_used", "five_reset", "5h"),
                                           ("week_used", "week_reset", "weekly")):
            used = lim.get(used_key)
            if used is None:
                continue
            remaining = max(0, 100 - used)
            head = tk.Frame(self.body, bg=BG)
            head.pack(fill="x", padx=12, pady=(4, 0))
            tk.Label(head, text="%s left %d%%" % (title, round(remaining)),
                     font=self.f_lim, fg=FG, bg=BG).pack(side="left")
            rl = tk.Label(head, text=format_reset(lim.get(reset_key)),
                          font=self.f_sub, fg=FG_MUTED, bg=BG)
            rl.pack(side="right")
            self.reset_labels.append((rl, lim.get(reset_key)))

            bar = tk.Canvas(self.body, height=6, width=bw, bg=BG, highlightthickness=0)
            bar.pack(fill="x", padx=12, pady=2)
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

        dsize = max(8, round(12 * self.scale))
        dot = tk.Canvas(row, width=dsize, height=dsize, bg=BG, highlightthickness=0)
        did = dot.create_oval(1, 1, dsize - 1, dsize - 1,
                              fill=DOT.get(status, FG_MUTED), outline="")
        dot.grid(row=0, column=0, rowspan=2, padx=(2, 9))

        proj = s.get("project") or "?"
        if len(proj) > NAME_MAX:
            proj = proj[:NAME_MAX - 1] + "…"
        title = proj if s.get("named") else "%s·%s" % (proj, (sid or "")[:6])
        tl = tk.Label(row, text=title, font=self.f_title, fg=FG, bg=BG, anchor="w")
        tl.grid(row=0, column=1, sticky="w")

        sub = tk.Frame(row, bg=BG)
        sub.grid(row=1, column=1, sticky="w")
        st_lbl = tk.Label(sub, text=LABEL.get(status, status), font=self.f_sub,
                          fg=STATUS_FG.get(status, FG_MUTED), bg=BG)
        st_lbl.pack(side="left")
        parts = [short_model(s.get("model") or "")]
        if s.get("tokens"):
            parts.append(format_tokens(s.get("tokens")) + " tok")
        meta = " · ".join(p for p in parts if p)
        if meta:
            tk.Label(sub, text=" · " + meta, font=self.f_sub,
                     fg=FG_MUTED, bg=BG).pack(side="left")

        al = tk.Label(row, text="", font=self.f_sub, fg=FG_MUTED, bg=BG)
        al.grid(row=0, column=2, rowspan=2, sticky="e", padx=(6, 4))

        self.row_widgets[sid] = {"dot": dot, "dot_id": did, "title": tl,
                                 "status": st_lbl, "age": al}

    # ---- age tick (in memory) ------------------------------------------------
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
