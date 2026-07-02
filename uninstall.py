#!/usr/bin/env python3
"""Remove the traffic-light hooks from ~/.claude/settings.json.

Run inside WSL:  python3 uninstall.py

Only strips hook groups whose command contains the 'traffic_hook.py' marker;
every other hook (e.g. your gsd hooks) is left untouched. Backs up first and
writes atomically. Does NOT touch the deployed Windows widget folder — delete
that by hand if you want it gone.
"""
import os
import json
import time
import shutil

SETTINGS = os.path.expanduser("~/.claude/settings.json")
STATUS_DIR = os.path.expanduser("~/.claude/traffic_status")
MARKER = "traffic_hook.py"
WRAPPER_MARKER = "statusline-ratelimit.sh"


def main():
    if not os.path.exists(SETTINGS):
        print("no settings.json; nothing to do.")
        return

    with open(SETTINGS, "r", encoding="utf-8") as f:
        data = json.load(f)
    shutil.copy2(SETTINGS, "%s.bak-%d" % (SETTINGS, int(time.time())))

    hooks = data.get("hooks", {})
    removed = 0
    for event, lst in list(hooks.items()):
        keep = [g for g in lst
                if not any(MARKER in h.get("command", "")
                           for h in g.get("hooks", []))]
        removed += len(lst) - len(keep)
        if keep:
            hooks[event] = keep
        else:
            del hooks[event]  # drop the event key if it's now empty

    # restore the statusLine if we wrapped it
    sl = data.get("statusLine", {})
    if WRAPPER_MARKER in sl.get("command", ""):
        orig = ""
        try:
            with open(os.path.join(STATUS_DIR, "__orig_statusline"),
                      "r", encoding="utf-8") as f:
                orig = f.read().strip()
        except Exception:
            pass
        if orig:
            sl["command"] = orig
            print("restored statusLine ->", orig)
        else:
            data.pop("statusLine", None)
            print("removed our statusLine wrapper (no original saved)")

    tmp = SETTINGS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, SETTINGS)
    print("removed %d traffic-light hook group(s) from %s" % (removed, SETTINGS))


if __name__ == "__main__":
    main()
