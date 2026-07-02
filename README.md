# 🚦 Claude Code 桌面会话面板(WSL → Windows 悬浮窗)

一个挂在 **Windows 桌面**上的无边框置顶悬浮小窗,列出你在 **WSL 里跑的每个 Claude Code 会话**当前是「运行中 / 已完成 / 待确认 / 空闲」,以及距上次活动多久 —— 多开几个项目时,余光一扫就知道哪个跑完了、哪个还在忙,不用挨个切窗口。

```
Claude Code
🔵 Jianghui-java17 · 3f2ab1   运行中     4s
🟢 RuoYi-Vue3      · a465cd   已完成    12s
🟡 keyword-tracker · d6e1f0   待确认     1m
```

---

## 来源与署名 · Attribution

**Forked from [weilizhe8-del/claude-code-traffic-light](https://github.com/weilizhe8-del/claude-code-traffic-light) (MIT).**
This is a modified version — 不是原版。原项目是 Windows 上的**单个聚合红绿灯**(PowerShell hook + tkinter),本 fork 在其之上做了以下改造:

- **hook 改用 Python 并读 stdin**:从 Claude Code 传入的 JSON 里取 `session_id` / `cwd`,支持在 WSL(Linux)里运行(原版是 PowerShell + 走进程树找 `claude.exe`)。
- **单聚合灯 → 每会话一行列表**:每个会话独立一行(项目名 + 短 id + 状态 + 距上次活动)。
- **数据通道**:每会话一个 JSON 文件;widget 跑在 Windows 侧、经 `\\wsl.localhost\...` UNC 读取,`-topmost` 才是真正的 `HWND_TOPMOST`(压得住原生 Windows 窗口)。
- 只监控 Claude Code;新增位置记忆、僵尸会话清理、两级刷新(读盘 2s / 就地跳秒 1s)。

原作者的多会话 slot 设计文档保留在 [`design_multi_window.md`](./design_multi_window.md)。`LICENSE` 保留原 MIT 全文及原作者版权声明。

---

## 架构

```
WSL (Ubuntu)                                Windows 桌面
Claude Code 会话
   │  生命周期 hook(stdin JSON)
   ▼
traffic_hook.py ──写──► ~/.claude/traffic_status/<session_id>.json
                        {status, ts, project, sid}
                                 │  \\wsl.localhost\<distro>\...\traffic_status\
                                 ▼
                        traffic_widget.py (pythonw + tkinter,置顶悬浮)
```

两端只靠文件解耦:hook 只管「写状态」,widget 只管「读+显示」。不开端口、不常驻服务,任一端崩了不影响另一端。

## 事件 → 状态映射

| Claude Code hook | 状态 | 说明 |
|---|---|---|
| `SessionStart` | 空闲(idle) | `source=="compact"`(上下文压缩)时不重置 |
| `UserPromptSubmit` | 运行中(running) | 你提交了 prompt,开始跑 |
| `Notification` | 待确认 / 空闲 | 按 `notification_type` 分流:`permission_prompt`→待确认;`idle_prompt`→空闲 |
| `Stop` | 已完成(finished) | 本轮答完,在等你 |
| `SessionEnd` | 移除 | 删掉该会话的行 |

> 若你开了 `defaultMode: auto` / `skipAutoPermissionPrompt`,权限提示极少触发,「待确认」基本不亮属正常 —— 实际常用的是 **运行中 / 已完成 / 空闲** 三态,正好回答「跑完了没」。

## 安装

**前置**:Windows 上装一个 Python(勾选 Add to PATH),含 tkinter(官方安装包默认带)。WSL 里有 `python3`。

```bash
# 在 WSL 里
python3 /opt/claude-traffic-light/install.py
# 若自动探测 Windows 主目录失败,手动指定:
# python3 install.py --win-dir /mnt/c/Users/<你>/claude-traffic-widget
```

install 会:① 把 hook **合并**进 `~/.claude/settings.json`(append,不动你已有的 hook,先自动备份);② 把 `traffic_widget.py` + `start_widget.cmd` 拷到 Windows 侧 `C:\Users\<你>\claude-traffic-widget\`,并在启动脚本里写好本机的 UNC 状态目录。

**装完重启你的 Claude Code 会话**让 hook 生效,然后在 Windows 上**双击 `start_widget.cmd`** 启动悬浮窗(`pythonw` 无黑框)。

## 使用

- 左键拖动挪位置(记忆,下次开在原地);右键关闭。
- 想开机自启:把 `start_widget.cmd` 的快捷方式丢进 `shell:startup`。
- 可调项都在 `traffic_widget.py` 顶部常量(刷新间隔、颜色、TTL、宽度)。

## 卸载

```bash
python3 /opt/claude-traffic-light/uninstall.py   # 只移除本工具的 hook,保留其它
```
Windows 侧的 `claude-traffic-widget` 文件夹自行删除。

## License

MIT —— 见 [`LICENSE`](./LICENSE)(保留原作者 `Copyright (c) 2026 weilizhe8` + 本 fork 修改版权)。
