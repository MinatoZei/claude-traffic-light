#!/usr/bin/env python3
"""Claude Code lifecycle hook -> per-session status file.

Invoked by Claude Code hooks (see install.py). Reads the hook JSON from stdin,
derives the session's current traffic-light status and writes it atomically to
  ~/.claude/traffic_status/<session_id>.json  = {status, ts, project, sid}
The desktop widget (traffic_widget.py) polls that directory.

HARD RULES (do not violate):
  * NEVER write to stdout. For SessionStart / UserPromptSubmit hooks Claude Code
    injects hook stdout into the model context, so any print() here would poison
    the conversation. Diagnostics go to stderr only.
  * Always swallow exceptions and exit 0 so a hook failure never breaks Claude.
  * Write atomically (tmp + os.replace) so the widget never reads a half file.

Forked from weilizhe8-del/claude-code-traffic-light (MIT). The status-file /
slot model is inspired by the original; the stdin parsing and event mapping are
rewritten for Linux/WSL + per-session listing.
"""
import sys
import os
import json
import time

STATUS_DIR = os.path.expanduser("~/.claude/traffic_status")
NAMES_FILE = os.path.join(STATUS_DIR, "__names")  # {sid: alias}, widget-written


def _slot(sid):
    return os.path.join(STATUS_DIR, "%s.json" % sid)


def load_alias(sid):
    """Per-session display alias set from the widget (✎ rename). Wins over
    every other name for the terminal title so a rename isn't clobbered back
    to the folder name by the next hook event."""
    try:
        with open(NAMES_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        return (d.get(sid) or "").strip() if isinstance(d, dict) else ""
    except Exception:
        return ""


def resolve_name(ev):
    """Display name for a session, most-specific wins:
       CCTL_NAME env  >  <cwd>/.cctl-name file  >  basename(cwd).
    Returns (name, named) where `named` means a custom name was found."""
    env = os.environ.get("CCTL_NAME", "").strip()
    if env:
        return env, True
    cwd = (ev.get("cwd") or "").rstrip("/")
    if cwd:
        try:
            with open(os.path.join(cwd, ".cctl-name"), "r", encoding="utf-8") as f:
                fn = f.read().strip()
            if fn:
                return fn, True
        except Exception:
            pass
    return (os.path.basename(cwd) or "?"), False


def parse_transcript(path):
    """Return (model, total_tokens) from a session .jsonl transcript.
    total_tokens = cumulative input+output+cache tokens across assistant turns
    (matches the Codex-style 'NNM tok' cumulative counter, cache reads included).
    Returns (None, None) on any failure so callers fall back to the last value."""
    model, total = None, 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                # cheap pre-filter: skip the many non-assistant lines fast
                if '"assistant"' not in line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get("type") != "assistant":
                    continue
                msg = o.get("message", {}) or {}
                if msg.get("model"):
                    model = msg["model"]
                u = msg.get("usage", {}) or {}
                total += ((u.get("input_tokens") or 0)
                          + (u.get("output_tokens") or 0)
                          + (u.get("cache_creation_input_tokens") or 0)
                          + (u.get("cache_read_input_tokens") or 0))
    except Exception:
        return None, None
    return model, total


STATUS_MARK = {"running": "🔵", "needs_confirmation": "🟡",
               "finished": "🟢", "idle": "⚪"}


def _find_tty():
    """Controlling pts of the session (walk ancestors — the hook's own fds are
    pipes, but the claude process / its shell sit on a /dev/pts/*)."""
    pid = os.getpid()
    for _ in range(15):
        for fd in (0, 1, 2):
            try:
                p = os.readlink("/proc/%d/fd/%d" % (pid, fd))
                if p.startswith("/dev/pts/"):
                    return p
            except OSError:
                pass
        try:
            with open("/proc/%d/stat" % pid, "rb") as f:
                ppid = int(f.read().rsplit(b")", 1)[1].split()[1])
        except Exception:
            return None
        if ppid <= 1:
            return None
        pid = ppid
    return None


def set_terminal_title(status, name, tty):
    """Write '🔵 name' into the tab title (OSC 0), straight to the session's
    pts — NOT stdout, so Claude's context stays clean. Turns anonymous 'Ubuntu'
    tabs into readable, per-session titles and gives the widget's
    click-to-jump matching something to find. Disable with CCTL_NO_TITLE=1.
    NOTE: only takes effect in launch modes where the terminal honors
    application titles (e.g. PowerShell tab -> `wsl`); the Windows Terminal
    Ubuntu profile force-pins the title to 'Ubuntu' (WSL#8701)."""
    if os.environ.get("CCTL_NO_TITLE") or not name or name == "?" or not tty:
        return
    try:
        with open(tty, "w") as t:
            t.write("\033]0;%s %s\007" % (STATUS_MARK.get(status, ""), name))
    except OSError:
        pass


def read_slot(sid):
    try:
        with open(_slot(sid), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def write_slot(sid, status, project, named, model=None, tokens=None, agents=None):
    os.makedirs(STATUS_DIR, exist_ok=True)
    prev = None
    if (not project or project == "?") or model is None or tokens is None \
            or agents is None:
        prev = read_slot(sid)
    # a later event without fresh data must not wipe previously known values
    if (not project or project == "?") and prev and \
            prev.get("project") and prev["project"] != "?":
        project = prev["project"]
        named = prev.get("named", named)
    if model is None and prev:
        model = prev.get("model")
    if tokens is None and prev:
        tokens = prev.get("tokens")
    if agents is None and prev:
        agents = prev.get("agents", 0)
    tty = _find_tty()
    if not tty:                      # e.g. no controlling pts on this event
        if prev is None:
            prev = read_slot(sid)
        tty = (prev or {}).get("tty")
    data = {"status": status, "ts": int(time.time()),
            "project": project or "?", "named": bool(named), "sid": sid,
            "model": model, "tokens": tokens, "agents": agents or 0,
            "tty": tty}              # lets the widget push a title immediately
    tmp = _slot(sid) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, _slot(sid))  # atomic
    # widget-side per-session alias (if any) beats CCTL_NAME / .cctl-name /
    # folder name for the tab title; the slot's project field stays the real
    # folder name (stickiness + jump matching depend on it).
    set_terminal_title(status, load_alias(sid) or data["project"], tty)


def remove_slot(sid):
    try:
        os.remove(_slot(sid))
    except FileNotFoundError:
        pass


def main():
    # status hint passed on the command line by install.py's hook config
    hint = sys.argv[1] if len(sys.argv) > 1 else ""

    ev = {}
    if not sys.stdin.isatty():
        raw = sys.stdin.read()
        if raw.strip():
            ev = json.loads(raw)

    sid = ev.get("session_id") or "unknown"
    project, named = resolve_name(ev)
    name = ev.get("hook_event_name", "")

    # model + token totals only refreshed on turn end / session start (low freq,
    # parsing the transcript is too heavy for every event); other events keep the
    # last known values via write_slot's stickiness.
    model = tokens = None
    if name in ("Stop", "SessionStart") and ev.get("transcript_path"):
        model, tokens = parse_transcript(ev["transcript_path"])

    # ---- event dispatch (event name wins over the argv hint) ----
    if name == "SessionEnd":
        remove_slot(sid)
        return

    if name == "SessionStart":
        # context compaction re-fires SessionStart mid-run; do NOT reset a
        # running session back to idle.
        if ev.get("source") == "compact":
            return
        write_slot(sid, "idle", project, named, model, tokens)
        return

    if name == "Notification":
        nt = ev.get("notification_type", "")
        if nt in ("permission_prompt", "elicitation_dialog"):
            write_slot(sid, "needs_confirmation", project, named)
        elif nt == "idle_prompt":
            write_slot(sid, "idle", project, named)
        # auth_success / elicitation_complete / ... : ignore
        return

    if name == "PostToolUse":
        # a tool just finished -> definitely working. This is what flips
        # needs_confirmation back to running after the user approves a
        # permission/plan prompt (approval itself fires no hook event).
        # Throttled: skip the disk write while already running with a fresh
        # heartbeat, so per-tool churn stays negligible.
        prev = read_slot(sid) or {}
        st = prev.get("status")
        if st == "finished":
            return                      # never resurrect a finished row
        if st == "running" and time.time() - (prev.get("ts") or 0) < 25:
            return
        write_slot(sid, "running", project, named)
        return

    if name in ("SubagentStart", "SubagentStop"):
        prev = read_slot(sid) or {}
        n = prev.get("agents", 0) or 0
        if name == "SubagentStart":
            n, status = n + 1, "running"       # dispatching = definitely working
        else:
            n, status = max(0, n - 1), prev.get("status") or "running"
        write_slot(sid, status, project, named, agents=n)
        return

    if name == "Stop":
        prev = read_slot(sid) or {}
        n = prev.get("agents", 0) or 0
        if n > 0:
            # turn ended but background subagents are still working
            # ("waiting for N background agents") -> NOT finished yet; the
            # main loop resumes when they return and a later Stop lands here
            # with n == 0.
            write_slot(sid, "running", project, named, model, tokens, agents=n)
        else:
            write_slot(sid, "finished", project, named, model, tokens, agents=0)
        return

    # UserPromptSubmit -> running (status comes from the hint)
    if hint:
        write_slot(sid, hint, project, named, model, tokens)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never break the Claude session
        sys.stderr.write("traffic_hook error: %r\n" % (e,))
    sys.exit(0)
