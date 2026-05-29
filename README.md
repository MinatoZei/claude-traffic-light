# 🚦 Claude Code Traffic Light

A tiny desktop widget that sits on your screen like a traffic light, showing Claude Code's real-time status at a glance.

**Yellow blinking** = Claude is processing  
**Red blinking** = Claude needs your confirmation  
**Green blinking** = Claude just finished  

## Screenshot

```
┌──────┐
│  🔴  │  Red    → Needs confirmation (Bash / Write / Edit)
│  🟡  │  Yellow → Running (processing your prompt)
│  🟢  │  Green  → Finished (auto-off after 5s)
└──────┘
  56 × 188 px  ·  Always on top  ·  Draggable
```

## How It Works

```
┌─────────────────┐     ┌──────────────────────┐
│ traffic_light.py │◄────│ traffic_status.json  │
│  (tkinter GUI)   │     │ %USERPROFILE%\.claude\│
│  polls every 0.5s│     └──────────────────────┘
└─────────────────┘               ▲
                                  │ writes
┌─────────────────┐     ┌──────────────────────┐
│  Claude Code     │────►│  .claude/settings.json│
│  hooks system    │     │  (UserPromptSubmit,   │
│                  │     │   PreToolUse, Stop…)  │
└─────────────────┘     └──────────────────────┘
```

Claude Code hooks detect state changes and write to a status file. The widget reads the file every 500ms and updates the lights.

## Install

```bash
git clone https://github.com/weilizhe8-del/claude-code-traffic-light.git
cd claude-code-traffic-light
```

**Zero dependencies** — uses only Python 3 + tkinter (bundled with Python on Windows).

## Usage

### 1. Start the widget

Double-click `start_traffic_light.cmd`, or run:

```powershell
pythonw traffic_light.py
```

A small traffic light appears on the right side of your screen. Drag it anywhere. Right-click to exit.

### 2. Configure Claude Code hooks

Copy the hooks configuration from `.claude/settings.json` into your own project's `.claude/settings.json` (or `~/.claude/settings.json` for global use). Also copy `.claude/hooks/traffic-update.cmd`.

Update the command paths in `settings.json` to match your local setup.

### 3. Use Claude Code normally

The lights change automatically:
- Submit a prompt → **yellow** blinking
- Claude asks for tool permission → **red** blinking
- Claude finishes responding → **green** blinking (5 seconds, then off)

## Files

| File | Purpose |
|------|---------|
| `traffic_light.py` | Main widget (tkinter, zero deps) |
| `start_traffic_light.cmd` | One-click launcher |
| `.claude/settings.json` | Hook definitions (4 hooks) |
| `.claude/hooks/traffic-update.cmd` | Status-file writer called by hooks |

## Requirements

- Windows 10 / 11
- Python 3.9+ (with tkinter — included in standard Python installer)
- Claude Code

## License

MIT
