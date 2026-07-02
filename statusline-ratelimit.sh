#!/usr/bin/env bash
# Claude Code statusLine passthrough that ALSO captures the real 5h / weekly rate
# limits into ~/.claude/traffic_status/ratelimits.json for the desktop widget.
#
# rate_limits is only present in the statusLine stdin for Claude.ai (Pro/Max)
# subscribers, and only after the first API response of a session. When it's
# absent we do NOT overwrite the last good snapshot (so the widget keeps showing
# the previous values / countdown instead of blanking).
#
# stdin is relayed UNCHANGED to the original statusLine command (saved in
# __orig_statusline by install.py), so your existing status bar keeps working.
D="$HOME/.claude/traffic_status"
mkdir -p "$D" 2>/dev/null
input=$(cat)

snap=$(printf '%s' "$input" | jq -c '{
  five_used:  (.rate_limits.five_hour.used_percentage  // null),
  five_reset: (.rate_limits.five_hour.resets_at        // null),
  week_used:  (.rate_limits.seven_day.used_percentage  // null),
  week_reset: (.rate_limits.seven_day.resets_at        // null),
  ts: now
}' 2>/dev/null)
if [ -n "$snap" ] && printf '%s' "$snap" | jq -e '.five_used!=null or .week_used!=null' >/dev/null 2>&1; then
  printf '%s' "$snap" > "$D/ratelimits.json.tmp" 2>/dev/null && \
    mv "$D/ratelimits.json.tmp" "$D/ratelimits.json" 2>/dev/null
fi

orig=$(cat "$D/__orig_statusline" 2>/dev/null)
if [ -n "$orig" ]; then
  printf '%s' "$input" | eval "$orig"
else
  printf '%s' "$input"
fi
