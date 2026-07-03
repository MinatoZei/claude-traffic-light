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
  * drag the right edge      -> resize width
  * drag the bottom edge / bottom-right corner -> proportional zoom
  * Ctrl + mouse wheel       -> proportional zoom too
  * right-click              -> context menu
  Titles are never truncated — the window widens to fit. Height fits the rows.
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
import re
import sys
import json
import time
import base64
import subprocess
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
# Claude Code's own per-process session files live next to traffic_status
SESSIONS_DIR = os.path.join(os.path.dirname(STATUS_DIR.rstrip("\\/")), "sessions")
NAMES_FILE = os.path.join(STATUS_DIR, "__names")   # {sid: alias} — per SESSION,
# not per project: several sessions often share one folder, and a rename must
# never leak onto other/new sessions started from the same directory.

# ---- tunables ---------------------------------------------------------------
DATA_POLL_MS = 2000
AGE_TICK_MS = 1000
DEAD_TTL = 6 * 3600
STALE = 30 * 60
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
STATUS_MARK = {"running": "🔵", "needs_confirmation": "🟡",  # keep = hook's
               "finished": "🟢", "idle": "⚪"}


def wsl_distro():
    """Distro name out of the \\\\wsl.localhost\\<distro>\\... status dir."""
    m = re.match(r"^\\\\wsl(?:\.localhost|\$)\\([^\\]+)", STATUS_DIR)
    return m.group(1) if m else None


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


def claude_session(s):
    """Claude Code's own live session file for this slot: its 'status' is
    'busy' while a background shell still runs AFTER the turn ended
    (something no hook event reports), and its 'name' updates the moment the
    user runs /rename. sessionId is verified against the slot (pid reuse).
    Returns the parsed dict, or None when unavailable/mismatched."""
    pid = s.get("cpid")
    if not pid:
        return None
    try:
        with open(os.path.join(SESSIONS_DIR, "%s.json" % pid),
                  "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if d.get("sessionId") == s.get("sid") else None
    except Exception:
        return None


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
        cs = claude_session(d)
        # turn ended (finished/idle) but Claude still reports busy = a
        # background shell is running -> the session is NOT done. Upgrade to
        # running with a bg marker; never touches needs_confirmation.
        if d.get("status") in ("finished", "idle") and \
                cs and cs.get("status") == "busy":
            d["status"], d["bg"] = "running", True
        # live name sync: /rename lands in sessions/<pid>.json instantly but
        # only reaches the slot file on the NEXT hook event — read it here so
        # a rename shows within one poll. nameSource "derived" is Claude's
        # startup placeholder ('opt-c7'), never a display name; when the
        # stored auto IS that placeholder (slots written before the hook
        # filtered it), drop it so the row falls back to folder·shortid.
        nm = ((cs.get("name") or "").strip()) if cs else ""
        if cs and nm and cs.get("nameSource") != "derived":
            d["auto"] = nm
        elif nm and (d.get("auto") or "").strip() == nm:
            d["auto"] = ""
        rows.append(d)
    rows.sort(key=lambda d: (ORDER.get(d.get("status"), 9), -d.get("ts", 0)))
    return rows


def load_names():
    try:
        with open(NAMES_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


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
        self.fingerprint = None      # content fingerprint -> in-place update
        self.struct_fp = None        # structural fingerprint -> full rebuild
        self.slots = {}
        self.names = {}
        self.row_widgets = {}
        self.limit_widgets = {}
        self.reset_labels = []
        self.row_order = []
        # sid -> (status, ts) the user acknowledged by clicking the dot;
        # any new event changes (status, ts) and re-arms the blink
        acked_raw = st.get("acked")
        self.acked = ({k: tuple(v) for k, v in acked_raw.items()}
                      if isinstance(acked_raw, dict) else {})

        # spacer pins the minimum window width (right-edge drag adjusts it;
        # long titles widen the window beyond it automatically)
        self.spacer = tk.Frame(self.root, bg=BG, width=self.width, height=1)
        self.spacer.pack()

        self.header = tk.Frame(self.root, bg=BG)
        self.header.pack(fill="x")
        self.head_lbl = tk.Label(self.header, text="Claude Code", font=self.f_head,
                                 fg=FG, bg=BG, anchor="w", padx=12, pady=5)
        self.head_lbl.pack(side="left")
        # collapsed-mode summary: "3会话 · 2运行 · 1空闲"
        self.sum_lbl = tk.Label(self.header, text="", font=self.f_sub,
                                fg=FG_MUTED, bg=BG, anchor="w")
        self.sum_lbl.pack(side="left")
        self.close_lbl = tk.Label(self.header, text="✕", font=self.f_toggle,
                                  fg=FG_MUTED, bg=BG, padx=10, pady=2,
                                  cursor="hand2")
        self.close_lbl.pack(side="right")
        self.close_lbl.bind("<Button-1>", lambda e: self.root.destroy())
        self.close_lbl.bind("<Enter>",
                            lambda e: self.close_lbl.config(fg="#ef4444"))
        self.close_lbl.bind("<Leave>",
                            lambda e: self.close_lbl.config(fg=FG_MUTED))
        self.toggle_lbl = tk.Label(self.header, text="▶" if self.collapsed else "▼",
                                   font=self.f_toggle, fg="#c3c8cf", bg=BG,
                                   padx=6, pady=2, cursor="hand2")
        self.toggle_lbl.pack(side="right")
        self.refresh_lbl = tk.Label(self.header, text="⟳", font=self.f_toggle,
                                    fg=FG_MUTED, bg=BG, padx=6, pady=2,
                                    cursor="hand2")
        self.refresh_lbl.pack(side="right")
        self.refresh_lbl.bind("<Button-1>", self._force_refresh)

        self.body = tk.Frame(self.root, bg=BG)
        # resize affordances (replace the old useless corner grip):
        #   right edge strip            -> drag = width
        #   bottom strip (whole, incl. corner) -> drag = proportional zoom
        self.edge_r = tk.Frame(self.root, bg=BG, width=6)
        self._set_cursor(self.edge_r, "size_we", "sb_h_double_arrow", "right_side")
        self.edge_b = tk.Frame(self.root, bg=BG, height=8)
        self._set_cursor(self.edge_b, "size_ns", "sb_v_double_arrow", "bottom_side")
        corner = tk.Canvas(self.edge_b, width=16, height=8, bg=BG,
                           highlightthickness=0)
        for off in (6, 11):                    # subtle corner ticks
            corner.create_line(off, 8, 16, off - 8, fill=FG_MUTED)
        corner.pack(side="right")
        self._set_cursor(corner, "size_nw_se", "bottom_right_corner", "sizing")
        for w in (self.edge_r, self.edge_b, corner):
            w.bind("<Button-1>", self._edge_press)
            w.bind("<ButtonRelease-1>", self._resize_release)
        self.edge_r.bind("<B1-Motion>", self._edge_w_drag)
        self.edge_b.bind("<B1-Motion>", self._zoom_drag)
        corner.bind("<B1-Motion>", self._zoom_drag)
        for w in (self.edge_r, self.edge_b):   # hover hint on the hot zones
            w.bind("<Enter>", lambda e, w_=w: w_.config(bg="#22252b"))
            w.bind("<Leave>", lambda e, w_=w: w_.config(bg=BG))
        if not self.collapsed:
            self._show_body()

        for w in (self.root, self.header, self.head_lbl, self.sum_lbl, self.body):
            self._bind_drag(w)
        # right-click ANYWHERE opens a small context menu (quitting directly on
        # right-click was too easy to trigger by accident — use ✕ or the menu)
        self.root.bind_all("<Button-3>", self._context_menu)
        for w in (self.header, self.head_lbl, self.sum_lbl):
            w.bind("<Double-Button-1>", self._toggle_collapse)
        self.toggle_lbl.bind("<Button-1>", self._toggle_collapse)  # single click
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
        self.f_toggle = (FAMILY, max(9, round(13 * s)))

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
        acked = {sid: list(v) for sid, v in self.acked.items()
                 if sid in self.slots}          # prune gone sessions
        st = {"pos": "+%d+%d" % (self.root.winfo_x(), self.root.winfo_y()),
              "width": self.width, "scale": round(self.scale, 2),
              "collapsed": self.collapsed, "acked": acked}
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

    @staticmethod
    def _set_cursor(w, *names):
        for cur in names:            # cursor names differ per platform
            try:
                w.configure(cursor=cur)
                return
            except tk.TclError:
                continue

    def _show_body(self):
        self.edge_b.pack(side="bottom", fill="x")
        self.edge_r.pack(side="right", fill="y")
        self.body.pack(fill="both", expand=True)

    def _toggle_collapse(self, e=None):
        self.collapsed = not self.collapsed
        if self.collapsed:
            self.body.pack_forget()
            self.edge_r.pack_forget()
            self.edge_b.pack_forget()
        else:
            self._show_body()
        self.toggle_lbl.config(text="▶" if self.collapsed else "▼")
        self._update_summary()
        self._save_state()

    # ---- edge resizing: right edge = width, bottom/corner = zoom -------------
    def _edge_press(self, e):
        self._rz = {"x": e.x_root, "y": e.y_root, "w": self.width,
                    "s": self.scale, "h": max(120, self.root.winfo_height()),
                    "applied": self.scale}

    def _edge_w_drag(self, e):
        w = self._rz["w"] + (e.x_root - self._rz["x"])
        self.width = min(MAX_WIDTH, max(MIN_WIDTH, w))
        self.spacer.config(width=self.width)

    def _zoom_drag(self, e):
        # dragging the bottom edge down/up zooms the whole widget in/out,
        # proportionally to how far you dragged relative to the window height
        dy = e.y_root - self._rz["y"]
        s = self._rz["s"] * (1 + dy / float(self._rz["h"]))
        s = min(MAX_SCALE, max(MIN_SCALE, round(s, 2)))
        if abs(s - self._rz["applied"]) < 0.05:
            return                   # throttle full rebuilds while dragging
        self._rz["applied"] = s
        self._apply_scale(s)

    def _resize_release(self, e=None):
        self._save_state()
        self.fingerprint = None      # bar widths depend on width -> rebuild
        self._sync()

    def _apply_scale(self, s):
        self.scale = s
        self._make_fonts()
        for w, f in ((self.head_lbl, self.f_head),
                     (self.toggle_lbl, self.f_toggle),
                     (self.close_lbl, self.f_toggle),
                     (self.refresh_lbl, self.f_toggle)):
            w.config(font=f)
        self.fingerprint = None
        self._sync()

    def _context_menu(self, e):
        m = tk.Menu(self.root, tearoff=0, bg="#1c1e22", fg=FG,
                    activebackground="#2a2d33", activeforeground=FG,
                    relief="flat", font=self.f_sub)
        m.add_command(label="⟳ 刷新限额", command=self._force_refresh)
        m.add_command(label=("▼ 展开" if self.collapsed else "▶ 收起"),
                      command=self._toggle_collapse)
        m.add_separator()
        m.add_command(label="✕ 关闭面板", command=self.root.destroy)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def _force_refresh(self, e=None):
        """⟳: drop the flag so the next statusLine render refreshes the limits
        snapshot (normally throttled to 10 min), and re-read everything now."""
        try:
            open(os.path.join(STATUS_DIR, "__limits_refresh"), "w").close()
        except OSError:
            pass
        self.fingerprint = None
        self._sync()
        self.refresh_lbl.config(fg="#3b82f6")           # click feedback
        self.root.after(600, lambda: self.refresh_lbl.config(fg=FG_MUTED))

    def _wheel(self, e):
        step = 0.05 if getattr(e, "delta", 0) > 0 else -0.05
        self._apply_scale(min(MAX_SCALE, max(MIN_SCALE,
                                             round(self.scale + step, 2))))
        self._save_state()

    # ---- data ---------------------------------------------------------------
    def _sync(self):
        slots = load_slots()
        lim = load_limits()
        self.names = load_names()
        self.slots = {s.get("sid", ""): s for s in slots}
        # structure = which rows / which limit bars exist + geometry. Only
        # this justifies a destroy-and-rebuild (visible flash); everything
        # else — texts, colors, tokens, status, even row ORDER — is applied
        # in place so routine status churn never makes the panel blink.
        struct = (tuple(sorted(s.get("sid", "") for s in slots)),
                  tuple(k for k in ("five_used", "week_used")
                        if lim and lim.get(k) is not None),
                  self.width, self.scale)
        lim_fp = ((round(lim.get("five_used") or -1),
                   round(lim.get("week_used") or -1),
                   lim.get("five_reset"), lim.get("week_reset"))
                  if lim else None)
        slot_fp = tuple((s.get("sid"), s.get("status"), s.get("bg"),
                         s.get("project"), s.get("named"), s.get("auto"),
                         s.get("model"), s.get("tokens"), s.get("agents"))
                        for s in slots)
        fp = (lim_fp, slot_fp, tuple(sorted(self.names.items())))
        if struct != self.struct_fp:
            self.struct_fp, self.fingerprint = struct, fp
            self._rebuild(slots, lim)
        elif fp != self.fingerprint:
            self.fingerprint = fp
            self._update(slots, lim)

    def data_poll(self):
        self._sync()
        self.root.after(DATA_POLL_MS, self.data_poll)

    # ---- rendering ----------------------------------------------------------
    def _rebuild(self, slots, lim):
        for child in self.body.winfo_children():
            child.destroy()
        self.row_widgets = {}
        self.limit_widgets = {}
        self.reset_labels = []
        self.row_order = [s.get("sid", "") for s in slots]
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
            hl = tk.Label(head, text="%s left %d%%" % (title, round(remaining)),
                          font=self.f_lim, fg=FG, bg=BG)
            hl.pack(side="left")
            rl = tk.Label(head, text=format_reset(lim.get(reset_key)),
                          font=self.f_sub, fg=FG_MUTED, bg=BG)
            rl.pack(side="right")
            self.reset_labels.append((rl, lim.get(reset_key)))

            bar = tk.Canvas(self.body, height=6, width=bw, bg=BG, highlightthickness=0)
            bar.pack(fill="x", padx=12, pady=2)
            bar.create_rectangle(0, 0, bw, 6, fill=BAR_TRACK, outline="")
            # fill rect always exists (maybe zero-width) so _update_limits can
            # resize/recolor it in place instead of rebuilding the canvas
            fill_id = bar.create_rectangle(0, 0, int(bw * remaining / 100.0), 6,
                                           fill=bar_color(remaining), outline="")
            self.limit_widgets[used_key] = {"title": title, "head": hl,
                                            "reset": rl, "bar": bar,
                                            "fill": fill_id}

    def _update_limits(self, lim):
        """In-place refresh of the limit bars (labels, fill width, color)."""
        self.reset_labels = []
        if not lim:
            return
        bw = max(60, self.width - 24)
        for used_key, reset_key in (("five_used", "five_reset"),
                                    ("week_used", "week_reset")):
            w = self.limit_widgets.get(used_key)
            used = lim.get(used_key)
            if not w or used is None:
                continue
            remaining = max(0, 100 - used)
            w["head"].config(text="%s left %d%%" % (w["title"], round(remaining)))
            w["reset"].config(text=format_reset(lim.get(reset_key)))
            self.reset_labels.append((w["reset"], lim.get(reset_key)))
            w["bar"].coords(w["fill"], 0, 0, int(bw * remaining / 100.0), 6)
            w["bar"].itemconfig(w["fill"], fill=bar_color(remaining))

    def _row_texts(self, s):
        """(title, status_text, meta_text) for a slot — single source shared
        by build and in-place update so the two can never drift apart."""
        sid = s.get("sid", "")
        proj = s.get("project") or "?"
        alias = self.names.get(sid)            # user rename (per session)
        auto = (s.get("auto") or "").strip()   # Claude's own session name
        # precedence: ✎ alias > CCTL_NAME/.cctl-name > Claude auto > folder;
        # never truncated — the window widens to fit the longest title
        shown = alias or (proj if s.get("named") else (auto or proj))
        if alias or s.get("named") or auto:    # already session-unique
            title = shown
        else:
            title = "%s·%s" % (shown, sid[:6])
        status = s.get("status") or ""
        agents = s.get("agents") or 0
        if status == "running" and agents > 0:
            st_text = "派%d个子代理中" % agents
        elif s.get("bg"):
            st_text = "后台任务中"
        else:
            st_text = LABEL.get(status, status)
        parts = [short_model(s.get("model") or "")]
        if s.get("tokens"):
            parts.append(format_tokens(s.get("tokens")) + " tok")
        meta = " · ".join(p for p in parts if p)
        return title, st_text, (" · " + meta) if meta else ""

    def _update(self, slots, lim):
        """Apply a data change to the existing widget tree — config() only,
        no destroy/recreate, so nothing flashes. Row order changes are done
        by re-packing the surviving frames in the new order."""
        self.head_lbl.config(text="Claude limits" if lim else "Claude Code")
        self._update_limits(lim)
        order = [s.get("sid", "") for s in slots]
        if order != self.row_order:
            for sid in order:
                w = self.row_widgets.get(sid)
                if w:
                    w["frame"].pack_forget()
            for sid in order:
                w = self.row_widgets.get(sid)
                if w:
                    w["frame"].pack(fill="x", padx=10, pady=3)
            self.row_order = order
        for s in slots:
            w = self.row_widgets.get(s.get("sid", ""))
            if not w:
                continue
            title, st_text, meta = self._row_texts(s)
            status = s.get("status") or ""
            w["title"].config(text=title)
            w["status"].config(text=st_text,
                               fg=STATUS_FG.get(status, FG_MUTED))
            w["meta"].config(text=meta)
        self._refresh_dynamic()

    def _build_row(self, s):
        sid = s.get("sid", "")
        status = s.get("status") or ""
        row = tk.Frame(self.body, bg=BG)
        row.pack(fill="x", padx=10, pady=3)
        row.columnconfigure(1, weight=1)

        dsize = max(8, round(12 * self.scale))
        dot = tk.Canvas(row, width=dsize, height=dsize, bg=BG, highlightthickness=0,
                        cursor="hand2")
        did = dot.create_oval(1, 1, dsize - 1, dsize - 1,
                              fill=DOT.get(status, FG_MUTED), outline="")
        dot.grid(row=0, column=0, rowspan=2, padx=(2, 9))
        dot.bind("<Button-1>", lambda e, s_=sid: self._ack(s_))

        title, st_text, meta = self._row_texts(s)
        tf = tk.Frame(row, bg=BG)
        tf.grid(row=0, column=1, sticky="w")
        tl = tk.Label(tf, text=title, font=self.f_title, fg=FG, bg=BG,
                      anchor="w", cursor="hand2")
        tl.pack(side="left")
        tl.bind("<Button-1>", lambda e, s_=sid: self._row_click(s_))
        tl.bind("<Double-Button-1>", lambda e, s_=sid: self._rename(s_))
        pen = tk.Label(tf, text="✎", font=self.f_sub, fg="#565d68", bg=BG,
                       cursor="hand2", padx=4)
        pen.pack(side="left")
        pen.bind("<Button-1>", lambda e, s_=sid: self._rename(s_))
        pen.bind("<Enter>", lambda e, p=pen: p.config(fg=FG))
        pen.bind("<Leave>", lambda e, p=pen: p.config(fg="#565d68"))

        sub = tk.Frame(row, bg=BG)
        sub.grid(row=1, column=1, sticky="w")
        st_lbl = tk.Label(sub, text=st_text, font=self.f_sub,
                          fg=STATUS_FG.get(status, FG_MUTED), bg=BG)
        st_lbl.pack(side="left")
        # meta label always exists (possibly empty) so _update can fill it
        # in place the moment model/tokens first become known
        meta_lbl = tk.Label(sub, text=meta, font=self.f_sub,
                            fg=FG_MUTED, bg=BG)
        meta_lbl.pack(side="left")

        al = tk.Label(row, text="", font=self.f_sub, fg=FG_MUTED, bg=BG)
        al.grid(row=0, column=2, rowspan=2, sticky="e", padx=(6, 4))

        # everything non-interactive should still drag the window
        for w in (row, sub, st_lbl, al, meta_lbl):
            self._bind_drag(w)

        self.row_widgets[sid] = {"frame": row, "dot": dot, "dot_id": did,
                                 "title": tl, "status": st_lbl,
                                 "meta": meta_lbl, "age": al}

    # ---- acknowledge (click the blinking dot = "seen it") --------------------
    def _ack(self, sid):
        s = self.slots.get(sid)
        if not s:
            return
        self.acked[sid] = (s.get("status"), s.get("ts"))
        self._save_state()
        self._refresh_dynamic()

    def _needs_attention(self, s):
        """finished / needs_confirmation that the user hasn't acknowledged."""
        if s.get("status") not in ("finished", "needs_confirmation"):
            return False
        return self.acked.get(s.get("sid", "")) != (s.get("status"), s.get("ts"))

    def _row_click(self, sid):
        """Click a row title: acknowledge + best-effort jump to its terminal."""
        self._ack(sid)
        s = self.slots.get(sid)
        if s:
            self._focus_terminal(s)

    def _focus_terminal(self, s):
        """Bring the window whose title mentions this session's folder to the
        foreground. Claude Code writes the folder name into the terminal title,
        so title matching finds the right window. Windows Terminal windows
        (CASCADIA class) are preferred over anything else (e.g. VS Code).
        Tab-level focus is impossible — WT has no per-tab API — so with many
        tabs in one window we can only raise that window. Windows-only no-op
        elsewhere."""
        if sys.platform != "win32":
            return
        # the tab title may carry the per-session alias (after a rename),
        # Claude's auto session name, or the raw folder name — try all three
        alias = (self.names.get(s.get("sid", "")) or "").strip()
        auto = (s.get("auto") or "").strip()
        proj = (s.get("project") or "").strip()
        needles = [n.lower() for n in (alias, auto, proj) if n and n != "?"]
        if not needles:
            return
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            # ONLY terminal/editor processes — matching arbitrary windows by
            # title raises browsers whose tabs mention the project name
            TERM_EXES = {"windowsterminal.exe", "openconsole.exe", "conhost.exe",
                         "wt.exe", "alacritty.exe", "wezterm-gui.exe",
                         "mintty.exe", "code.exe", "cursor.exe"}
            wt_hits, other_hits = [], []

            def exe_of(hwnd):
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                h = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED
                if not h:
                    return ""
                try:
                    buf = ctypes.create_unicode_buffer(260)
                    size = wintypes.DWORD(260)
                    if kernel32.QueryFullProcessImageNameW(h, 0, buf,
                                                           ctypes.byref(size)):
                        return os.path.basename(buf.value).lower()
                    return ""
                finally:
                    kernel32.CloseHandle(h)

            @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            def cb(hwnd, _):
                if not user32.IsWindowVisible(hwnd):
                    return True
                tb = ctypes.create_unicode_buffer(512)
                user32.GetWindowTextW(hwnd, tb, 512)
                if not tb.value:
                    return True
                low = tb.value.lower()
                if not any(n in low for n in needles):
                    return True
                exe = exe_of(hwnd)
                if exe not in TERM_EXES:
                    return True
                (wt_hits if exe in ("windowsterminal.exe", "wt.exe")
                 else other_hits).append(hwnd)
                return True

            user32.EnumWindows(cb, 0)
            hits = wt_hits or other_hits
            if not hits:
                return                                    # no jump beats a wrong jump
            hwnd = hits[0]
            user32.ShowWindow(hwnd, 9)                    # SW_RESTORE
            user32.keybd_event(0x12, 0, 0, 0)             # Alt down: allows
            user32.SetForegroundWindow(hwnd)              # SetForegroundWindow
            user32.keybd_event(0x12, 0, 2, 0)             # Alt up
        except Exception:
            pass

    # ---- rename (double-click a row title) -----------------------------------
    def _save_names(self):
        # keyed by sid (session-scoped); prune sessions that are gone — this
        # also flushes any legacy project-keyed entries from older versions
        self.names = {k: v for k, v in self.names.items() if k in self.slots}
        try:
            tmp = NAMES_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.names, f, ensure_ascii=False)
            os.replace(tmp, NAMES_FILE)
        except OSError:
            pass

    def _push_title(self, s, name):
        """Rewrite the session's terminal tab title right now via wsl.exe (the
        hook keeps it in sync on later events, but that only fires on the next
        event). Best effort: silently skipped without a recorded tty / off
        Windows / on any failure."""
        tty = (s or {}).get("tty")
        if sys.platform != "win32" or not tty or not name or name == "?":
            return
        try:
            cmd = ["wsl.exe"]
            d = wsl_distro()
            if d:
                cmd += ["-d", d]
            mark = STATUS_MARK.get(s.get("status"), "")
            title = ("%s %s" % (mark, name)).strip()
            # two traps here, both verified against the real wsl.exe:
            #  * MUST be -e (exec) — with `--` the trailing positional args
            #    never reach sh ($1 stays empty, argc=0);
            #  * non-ASCII argv gets mangled by the Windows codepage on the
            #    way through wsl.exe (GBK -> mojibake -> WT drops the OSC),
            #    so the title crosses as base64 and decodes on the Linux side.
            b64 = base64.b64encode(title.encode("utf-8")).decode("ascii")
            cmd += ["-e", "sh", "-c",
                    'printf "\\033]0;%s\\007" '
                    '"$(printf %s "$1" | base64 -d)" > ' + tty,
                    "sh", b64]
            subprocess.Popen(cmd, creationflags=0x08000000,     # NO_WINDOW
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def _rename(self, sid):
        s = self.slots.get(sid)
        if not s:
            return
        top = tk.Toplevel(self.root)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.configure(bg=BAR_TRACK)
        top.geometry("+%d+%d" % (self.root.winfo_pointerx() + 8,
                                 self.root.winfo_pointery() + 8))
        entry = tk.Entry(top, font=self.f_title, bg="#1c1e22", fg=FG,
                         insertbackground=FG, relief="flat", width=16)
        entry.insert(0, self.names.get(sid, ""))
        entry.pack(padx=2, pady=2)

        def done(save):
            if save:
                v = entry.get().strip()
                if v:
                    self.names[sid] = v
                else:
                    self.names.pop(sid, None)   # empty = back to folder name
                self._save_names()
                # sync the terminal tab title immediately; clearing reverts to
                # what the hook would write (auto name / folder name)
                if not v and not s.get("named"):
                    fallback = (s.get("auto") or "").strip() or s.get("project")
                else:
                    fallback = s.get("project")
                self._push_title(s, v or fallback or "")
                self.fingerprint = None
                self._sync()
            top.destroy()

        entry.bind("<Return>", lambda e: done(True))
        entry.bind("<Escape>", lambda e: done(False))
        entry.bind("<FocusOut>", lambda e: done(False))
        top.focus_force()
        entry.focus_set()

    # ---- age tick (in memory) ------------------------------------------------
    def age_tick(self):
        self.blink_on = not self.blink_on
        self._refresh_dynamic()
        self.root.after(AGE_TICK_MS, self.age_tick)

    def _update_summary(self):
        if not self.collapsed:
            self.sum_lbl.config(text="")
            return
        slots = list(self.slots.values())
        if not slots:
            self.sum_lbl.config(text="无会话", fg=FG_MUTED)
            return
        counts = {}
        for s in slots:
            st = s.get("status") or "idle"
            counts[st] = counts.get(st, 0) + 1
        parts = ["%d会话" % len(slots)]
        for st, word in (("needs_confirmation", "待确认"), ("running", "运行"),
                         ("finished", "完成"), ("idle", "空闲")):
            if counts.get(st):
                parts.append("%d%s" % (counts[st], word))
        fg = DOT["needs_confirmation"] if counts.get("needs_confirmation") else FG_MUTED
        if any(self._needs_attention(s) for s in slots) and not self.blink_on:
            fg = FG_STALE                     # soft blink while collapsed
        self.sum_lbl.config(text=" · ".join(parts), fg=fg, font=self.f_sub)

    def _refresh_dynamic(self):
        now = time.time()
        self._update_summary()
        for lbl, epoch in self.reset_labels:
            lbl.config(text=format_reset(epoch))
        for sid, w in self.row_widgets.items():
            s = self.slots.get(sid)
            if not s:
                continue
            status = s.get("status")
            age = now - s.get("ts", now)
            w["age"].config(text=format_age(age))
            # bg rows are re-verified live against Claude's session file every
            # poll, so a long background shell must not grey out as stale
            stale = (status == "running" and age > STALE and not s.get("bg"))
            w["title"].config(fg=FG_STALE if stale else FG)
            # finished / needs_confirmation blink until clicked (acknowledged)
            if self._needs_attention(s) and not self.blink_on:
                color = BG
            else:
                color = DOT.get(status, FG_MUTED)
            w["dot"].itemconfig(w["dot_id"], fill=color)


if __name__ == "__main__":
    Widget()
