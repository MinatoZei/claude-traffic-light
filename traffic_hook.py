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


def _slot(sid):
    return os.path.join(STATUS_DIR, "%s.json" % sid)


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


def write_slot(sid, status, project, named, model=None, tokens=None):
    os.makedirs(STATUS_DIR, exist_ok=True)
    prev = None
    if (not project or project == "?") or model is None or tokens is None:
        try:
            with open(_slot(sid), "r", encoding="utf-8") as f:
                prev = json.load(f)
        except Exception:
            prev = None
    # a later event without fresh data must not wipe previously known values
    if (not project or project == "?") and prev and \
            prev.get("project") and prev["project"] != "?":
        project = prev["project"]
        named = prev.get("named", named)
    if model is None and prev:
        model = prev.get("model")
    if tokens is None and prev:
        tokens = prev.get("tokens")
    data = {"status": status, "ts": int(time.time()),
            "project": project or "?", "named": bool(named), "sid": sid,
            "model": model, "tokens": tokens}
    tmp = _slot(sid) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, _slot(sid))  # atomic


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

    # UserPromptSubmit -> running, Stop -> finished (status comes from the hint)
    if hint:
        write_slot(sid, hint, project, named, model, tokens)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never break the Claude session
        sys.stderr.write("traffic_hook error: %r\n" % (e,))
    sys.exit(0)
