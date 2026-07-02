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
STATUSLINE_WRAPPER = os.path.join(HERE, "statusline-ratelimit.sh")
SETTINGS = os.path.expanduser("~/.claude/settings.json")
STATUS_DIR = os.path.expanduser("~/.claude/traffic_status")
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


def install_limits():
    """Wrap the existing statusLine so we can capture real 5h/weekly rate limits.
    Saves the original command to __orig_statusline; idempotent (won't double
    wrap); relays stdin to the original so the status bar keeps working."""
    wrapper_cmd = 'bash "%s"' % STATUSLINE_WRAPPER
    os.makedirs(STATUS_DIR, exist_ok=True)
    orig_file = os.path.join(STATUS_DIR, "__orig_statusline")

    data = {}
    if os.path.exists(SETTINGS):
        with open(SETTINGS, "r", encoding="utf-8") as f:
            data = json.load(f)
        shutil.copy2(SETTINGS, "%s.bak-%d" % (SETTINGS, int(time.time())))

    sl = data.setdefault("statusLine", {})
    cur = sl.get("command", "")
    if cur and cur != wrapper_cmd:
        with open(orig_file, "w", encoding="utf-8") as f:
            f.write(cur)  # remember what to relay to (once)
    elif not cur and not os.path.exists(orig_file):
        # no prior statusline: relay to nothing (wrapper just echoes input)
        open(orig_file, "w").close()
    sl["type"] = "command"
    sl["command"] = wrapper_cmd

    tmp = SETTINGS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, SETTINGS)
    try:
        os.chmod(STATUSLINE_WRAPPER, 0o755)
    except OSError:
        pass
    print("[limits] statusLine wrapped ->", wrapper_cmd)
    print("[limits] original relayed via:", open(orig_file).read().strip() or "(none)")
    print("[limits] real 5h/weekly bars need a Pro/Max plan; they appear after")
    print("[limits] the next session's first response writes ratelimits.json")


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


def find_pythonw():
    """Absolute Windows path to pythonw.exe (windowless). We can't rely on PATH:
    the python.org installer often isn't added, and WSL sees a stale Windows PATH.
    Falls back to the 'pyw' launcher (always in C:\\Windows)."""
    import glob
    for pat in ("/mnt/c/Users/*/AppData/Local/Programs/Python/Python*/pythonw.exe",
                "/mnt/c/Program Files/Python*/pythonw.exe",
                "/mnt/c/Program Files (x86)/Python*/pythonw.exe"):
        hits = sorted(glob.glob(pat))
        if hits:
            try:
                return subprocess.check_output(["wslpath", "-w", hits[-1]]).decode().strip()
            except Exception:
                pass
    return "pyw"


def _to_win(path):
    return subprocess.check_output(["wslpath", "-w", path]).decode().strip()


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
    pyw = find_pythonw()
    cmd_path = os.path.join(win_dir, "start_widget.cmd")
    cmd = ('@echo off\r\n'
           'set "CLAUDE_TRAFFIC_DIR=%s"\r\n'
           'start "" "%s" "%%~dp0traffic_widget.py"\r\n') % (unc, pyw)
    with open(cmd_path, "w", newline="") as f:
        f.write(cmd)
    print("[widget] deployed ->", win_dir)
    print("[widget] pythonw:", pyw)
    print("[widget] status dir (UNC):", unc)

    # autostart on login (silent, no console flash) via a Startup-folder .vbs
    startup = os.path.join(os.path.dirname(win_dir),
                           "AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup")
    if os.path.isdir(startup):
        try:
            vbs = ('CreateObject("WScript.Shell").Run """%s""", 0, False\r\n'
                   % _to_win(cmd_path))
            with open(os.path.join(startup, "claude-traffic-widget.vbs"),
                      "w", newline="") as f:
                f.write(vbs)
            print("[widget] autostart installed (runs on Windows login)")
        except Exception as e:
            print("[widget] autostart skipped:", e)
    print("[widget] double-click start_widget.cmd on Windows to launch")


if __name__ == "__main__":
    install_hooks()
    if "--with-limits" in sys.argv:
        install_limits()
    deploy_widget()
    print("done. restart your Claude Code sessions so the hooks take effect.")
