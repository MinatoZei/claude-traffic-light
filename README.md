# 🚦 Claude Code Traffic Light · 桌面红绿灯

<p align="center">
  <strong>Real-time desktop status indicator for Claude Code CLI — like a traffic light for your AI agent.</strong><br>
  <strong>Claude Code 命令行桌面状态指示器 — AI 编程时余光一扫，就知道 Claude 在干嘛。</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.9+-blue" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey" alt="Windows 10/11">
  <img src="https://img.shields.io/badge/dependencies-zero-brightgreen" alt="Zero dependencies">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License">
  <img src="https://img.shields.io/badge/topics-claude--code%20%7C%20desktop%20widget%20%7C%20tkinter-blueviolet" alt="Topics">
</p>

---

## Table of Contents · 目录

- [What it looks like · 长这样](#what-it-looks-like--长这样)
- [How it works · 原理](#how-it-works--原理)
- [Quick Start · 快速开始](#quick-start--快速开始)
- [State Diagram · 状态流转](#state-diagram--状态流转)
- [Files · 文件说明](#files--文件说明)
- [Customization · 自定义](#customization--自定义)
- [Troubleshooting · 故障排查](#troubleshooting--故障排查)
- [License](#license)

---

## What it looks like · 长这样

```
        ┌──────┐
        │  🔴  │ ← Red 红灯 — Needs confirmation 等待确认
        │  🟡  │ ← Yellow 黄灯 — Running 正在运行
        │  🟢  │ ← Green 绿灯 — Finished 运行完成
        │Done! │
        └──────┘
      56×188 px · always-on-top 置顶 · draggable 可拖拽
```

A tiny black rounded-rectangle sits on your desktop, always on top. The active light blinks so you can spot it from the corner of your eye.

一个黑色圆角小方块贴在桌面上，始终置顶。活跃的灯会闪烁，余光一扫就知道 Claude 在干嘛。

---

## How it works · 原理

```
┌──────────────────┐          ┌────────────────────────┐
│  traffic_light.py │  reads   │  traffic_status.json   │
│  (tkinter widget) │◄─────────│  ~/.claude/            │
│  polls every 0.5s │          └────────────────────────┘
└──────────────────┘                    ▲
                                        │ writes
┌──────────────────┐          ┌────────────────────────┐
│  Claude Code      │─────────►│  .claude/settings.json │
│  hook events      │          │  UserPromptSubmit      │
│                   │          │  PreToolUse / Post     │
│                   │          │  Stop                  │
└──────────────────┘          └────────────────────────┘
```

1. Claude Code fires hooks when its state changes (prompt submitted, tool permission requested, response finished)
2. Hooks run `traffic-update.cmd` which writes a tiny JSON file
3. The Python widget reads the JSON every 500ms and updates the lights

---

## Quick Start · 快速开始

### Prerequisites · 前提

- **Windows 10 or 11**
- **Python 3.9+** with tkinter (included in the standard Python installer)
- **Claude Code** (any recent version)

### Step 1 — Clone

```bash
git clone https://github.com/weilizhe8-del/claude-code-traffic-light.git
cd claude-code-traffic-light
```

### Step 2 — Start the widget · 启动红绿灯

Double-click `start_traffic_light.cmd`, or:

```powershell
pythonw traffic_light.py
```

A traffic light appears on the right side of your screen. **Drag** it anywhere with the left mouse button. **Right-click** to exit.

双击 `start_traffic_light.cmd`，屏幕右侧出现红绿灯。**左键拖拽**移动位置，**右键**退出。

### Step 3 — Configure hooks · 配置 hooks

The hooks configuration lives in `.claude/settings.json`. You need to copy it into the Claude Code project you want to monitor.

**Option A: Single project** — copy `.claude/settings.json` and `.claude/hooks/traffic-update.cmd` into your project's `.claude/` directory.

**Option B: All projects (global)** — merge the `hooks` section into `%USERPROFILE%\.claude\settings.json`, and place `traffic-update.cmd` somewhere on your PATH (or use an absolute path in the hook command).

将 `.claude/settings.json` 和 `.claude/hooks/traffic-update.cmd` 复制到你的 Claude Code 项目的 `.claude/` 目录下即可。

### Step 4 — Use Claude Code normally · 开始使用

Restart Claude Code (hooks are loaded at startup), then use it as usual. The lights change automatically:

| Light · 灯 | Status · 状态 | Trigger · 触发条件 |
|:---:|:---|:---|
| 🔴 Red 红 | **Needs confirmation** 等待确认 | Claude wants to run Bash / Write / Edit |
| 🟡 Yellow 黄 | **Running** 正在运行 | You submitted a prompt, Claude is thinking |
| 🟢 Green 绿 | **Finished** 运行完成 | Claude just responded (auto-off after 5s) |
| ⚫ All off 全灭 | **Idle** 空闲 | Waiting for your next prompt |

---

## State Diagram · 状态流转

```
  idle ──(UserPromptSubmit hook)──► running
                                      │
                            ┌─────────┴──────────┐
                            │  PreToolUse hook    │
                            │  (Bash/Write/Edit)  │
                            └─────────┬──────────┘
                                      ▼
                            needs_confirmation (red)
                                      │
                            ┌─────────┴──────────┐
                            │  PostToolUse hook   │
                            └─────────┬──────────┘
                                      ▼
                                   running (yellow)
                                      │
                            ┌─────────┴──────────┐
                            │  Stop hook          │
                            └─────────┬──────────┘
                                      ▼
                                  finished (green, 5s)
                                      │
                                      ▼
                                    idle
```

---

## Files · 文件说明

| File | Purpose |
|:------|:--------|
| `traffic_light.py` | Main widget — zero dependencies, pure Python + tkinter |
| `start_traffic_light.cmd` | One-click launcher (Windows batch) |
| `.claude/settings.json` | Claude Code hook definitions |
| `.claude/hooks/traffic-update.cmd` | One-line script that writes the status JSON |
| `LICENSE` | MIT |

---

## Customization · 自定义

All the knobs are at the top of `traffic_light.py`:

```python
POLL_MS = 500          # refresh interval (ms)
FINISHED_TTL = 5       # how long green stays on (seconds)
W, H = 56, 188         # window size (pixels)
LIGHT_R = 18           # circle radius
```

Color scheme — edit the `C` dict:

```python
C = {
    "running":            ("#ffcc00", "#665500"),   # (bright, dim)
    "needs_confirmation": ("#ff1a1a", "#660000"),
    "finished":           ("#00cc44", "#004400"),
}
```

---

## Troubleshooting · 故障排查

**Lights don't change · 灯不变化**
- Make sure you restarted Claude Code after adding the hooks configuration.
- Check that `.claude/settings.json` and `.claude/hooks/traffic-update.cmd` are present in the project you're running `claude` in.
- Verify `%USERPROFILE%\.claude\traffic_status.json` exists and is being written to.

**Widget window not showing · 窗口看不到**
- The window appears at the right edge of your screen, vertically centered. Check if it's behind other windows (use Alt+Tab to find it, though it has no taskbar entry).
- If you have multiple monitors, it appears on the primary monitor.

**Path errors in hooks · 路径错误**
- The hook command uses a relative path: `.claude\\hooks\\traffic-update.cmd`. Claude Code runs hook commands from the project root. If this doesn't work on your system, replace it with an absolute path in `settings.json`.

---

## License

MIT — see [LICENSE](./LICENSE).

---

<!--
  Keywords for discovery:
  Claude Code desktop widget, Claude Code traffic light, Claude Code status indicator,
  Claude Code hooks tutorial, Claude Code Windows tool, Claude Code GUI companion,
  tkinter desktop pet, Python desktop widget, AI coding assistant status monitor,
  Claude Code CLI helper, Claude Code权限监控, Claude Code状态指示器,
  Claude Code桌面组件, Claude Code红绿灯, Claude Code hooks配置,
  AI编程辅助工具, 桌面悬浮窗, 系统状态监控
-->
