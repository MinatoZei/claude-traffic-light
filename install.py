#!/usr/bin/env python3
"""Install the traffic-light hooks + deploy the desktop widget.

Run inside WSL:  python3 install.py  [--win-dir /mnt/c/Users/<you>/claude-traffic-widget]

Does two things:
  1. MERGES our hook commands into ~/.claude/settings.json. It appends to any
     existing hook arrays (your gsd hooks are preserved), is idempotent (re-runs
     don't stack duplicates, matched by the 'traffic_hook.py' marker), backs up
     the file first, and writes atomically.
  2. Copies traffic_widget.py + a start_widget.cmd launcher to a Windows-side
     folder so you can double-click it. The launcher hard-codes the correct
     \\wsl.localhost UNC status dir for this distro/user.
"""
import os
import sys
import json
import time
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK_PATH = os.path.join(HERE, "traffic_hook.py")
WIDGET_SRC = os.path.join(HERE, "traffic_widget.py")
SETTINGS = os.path.expanduser("~/.claude/settings.json")
MARKER = "traffic_hook.py"
PYBIN = sys.executable or "python3"

# event -> status hint passed to the hook on the command line
OUR = {
    "SessionStart": "idle",
    "UserPromptSubmit": "running",
    "Notification": "needs_confirmation",
    "Stop": "finished",
    "SessionEnd": "end",
}


def make_group(event, status):
    g: dict = {"hooks": [{"type": "command",
                          "command": '%s "%s" %s' % (PYBIN, HOOK_PATH, status),
                          "timeout": 5}]}
    if event == "Notification":
        g["matcher"] = ""  # all notification types; the hook itself filters
    return g


def install_hooks():
    data = {}
    if os.path.exists(SETTINGS):
        with open(SETTINGS, "r", encoding="utf-8") as f:
            data = json.load(f)
        bak = "%s.bak-%d" % (SETTINGS, int(time.time()))
        shutil.copy2(SETTINGS, bak)
        print("[hooks] backed up ->", bak)
    else:
        os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)

    hooks = data.setdefault("hooks", {})
    for event, status in OUR.items():
        lst = hooks.setdefault(event, [])            # keep existing groups
        # drop any previous group of ours (idempotent / self-healing on path change)
        lst[:] = [g for g in lst
                  if not any(MARKER in h.get("command", "")
                             for h in g.get("hooks", []))]
        lst.append(make_group(event, status))

    tmp = SETTINGS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, SETTINGS)
    print("[hooks] merged into", SETTINGS)


def detect_win_dir():
    for i, a in enumerate(sys.argv):
        if a == "--win-dir" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    try:
        out = subprocess.check_output(["cmd.exe", "/c", "echo %USERPROFILE%"],
                                      stderr=subprocess.DEVNULL, timeout=10)
        winhome = out.decode(errors="ignore").strip()          # C:\Users\minato
        wsl = subprocess.check_output(["wslpath", "-u", winhome],
                                      timeout=10).decode().strip()
        return os.path.join(wsl, "claude-traffic-widget")
    except Exception:
        return None


def deploy_widget():
    win_dir = detect_win_dir()
    if not win_dir:
        print("[widget] could not detect Windows home; skipped.")
        print("         re-run: python3 install.py --win-dir "
              "/mnt/c/Users/<you>/claude-traffic-widget")
        return
    os.makedirs(win_dir, exist_ok=True)
    shutil.copy2(WIDGET_SRC, os.path.join(win_dir, "traffic_widget.py"))

    distro = os.environ.get("WSL_DISTRO_NAME", "Ubuntu")
    wsl_status = os.path.expanduser("~/.claude/traffic_status")
    unc = r"\\wsl.localhost\%s%s" % (distro, wsl_status.replace("/", "\\"))
    cmd = ('@echo off\r\n'
           'set "CLAUDE_TRAFFIC_DIR=%s"\r\n'
           'start "" pythonw "%%~dp0traffic_widget.py"\r\n') % unc
    with open(os.path.join(win_dir, "start_widget.cmd"), "w", newline="") as f:
        f.write(cmd)

    print("[widget] deployed ->", win_dir)
    print("[widget] status dir (UNC):", unc)
    print("[widget] double-click start_widget.cmd on Windows to launch")


if __name__ == "__main__":
    install_hooks()
    deploy_widget()
    print("done. restart your Claude Code sessions so the hooks take effect.")
