#!/usr/bin/env bash
# Claude Code statusLine passthrough that ALSO captures the real 5h / weekly rate
# limits into ~/.claude/traffic_status/ratelimits.json for the desktop widget.
#
# No network requests are ever made here: rate_limits arrives for free in the
# statusLine stdin that Claude Code renders anyway. We merely copy 4 fields to a
# local file. Because statusLine renders very often, the snapshot write is
# THROTTLED to once per 10 minutes — unless the widget's ⟳ button drops the
# __limits_refresh flag file, which forces the next render to refresh it.
#
# rate_limits is only present for Claude.ai (Pro/Max) subscribers after the
# session's first API response; when absent we never clobber the last snapshot.
# stdin is relayed UNCHANGED to the original statusLine command (saved in
# __orig_statusline by install.py).
D="$HOME/.claude/traffic_status"
RL="$D/ratelimits.json"
FORCE="$D/__limits_refresh"
THROTTLE=600   # seconds between snapshot refreshes
mkdir -p "$D" 2>/dev/null
input=$(cat)

need=1
if [ -f "$RL" ] && [ ! -f "$FORCE" ]; then
  now=$(date +%s)
  mt=$(stat -c %Y "$RL" 2>/dev/null || echo 0)
  [ $((now - mt)) -lt "$THROTTLE" ] && need=0
fi

if [ "$need" = 1 ]; then
  snap=$(printf '%s' "$input" | jq -c '{
    five_used:  (.rate_limits.five_hour.used_percentage  // null),
    five_reset: (.rate_limits.five_hour.resets_at        // null),
    week_used:  (.rate_limits.seven_day.used_percentage  // null),
    week_reset: (.rate_limits.seven_day.resets_at        // null),
    ts: now
  }' 2>/dev/null)
  if [ -n "$snap" ] && printf '%s' "$snap" | jq -e '.five_used!=null or .week_used!=null' >/dev/null 2>&1; then
    printf '%s' "$snap" > "$RL.tmp" 2>/dev/null && mv "$RL.tmp" "$RL" 2>/dev/null
    rm -f "$FORCE" 2>/dev/null
  fi
fi

orig=$(cat "$D/__orig_statusline" 2>/dev/null)
if [ -n "$orig" ]; then
  printf '%s' "$input" | eval "$orig"
else
  printf '%s' "$input"
fi
