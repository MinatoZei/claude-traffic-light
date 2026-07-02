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


def write_slot(sid, status, project):
    os.makedirs(STATUS_DIR, exist_ok=True)
    data = {"status": status, "ts": int(time.time()), "project": project, "sid": sid}
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
    project = os.path.basename((ev.get("cwd") or "").rstrip("/")) or "?"
    name = ev.get("hook_event_name", "")

    # ---- event dispatch (event name wins over the argv hint) ----
    if name == "SessionEnd":
        remove_slot(sid)
        return

    if name == "SessionStart":
        # context compaction re-fires SessionStart mid-run; do NOT reset a
        # running session back to idle.
        if ev.get("source") == "compact":
            return
        write_slot(sid, "idle", project)
        return

    if name == "Notification":
        nt = ev.get("notification_type", "")
        if nt in ("permission_prompt", "elicitation_dialog"):
            write_slot(sid, "needs_confirmation", project)
        elif nt == "idle_prompt":
            write_slot(sid, "idle", project)
        # auth_success / elicitation_complete / ... : ignore
        return

    # UserPromptSubmit -> running, Stop -> finished (status comes from the hint)
    if hint:
        write_slot(sid, hint, project)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never break the Claude session
        sys.stderr.write("traffic_hook error: %r\n" % (e,))
    sys.exit(0)
