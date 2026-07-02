# 🚦 Claude Code 桌面会话面板(WSL → Windows 悬浮窗)

一个挂在 **Windows 桌面**上的无边框置顶悬浮小窗,列出你在 **WSL 里跑的每个 Claude Code 会话**当前是「运行中 / 已完成 / 待确认 / 空闲」,以及距上次活动多久 —— 多开几个项目时,余光一扫就知道哪个跑完了、哪个还在忙,不用挨个切窗口。

```
Claude limits
5h left 90%                     3h17m
██████████████████░░
weekly left 85%                 4d22h
█████████████████░░░
🔵 后端                          4s
   opus-4-8 · 35M tok
🟢 RuoYi-Vue3·a465cd            12s
   sonnet-5 · 26M tok
🟡 爬虫                          1m
   haiku-4-5 · 1M tok
```

状态点颜色:🔵 运行中 · 🟢 已完成/空闲 · 🟡 待确认(闪烁)。

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

### 给会话起名字

默认那行显示 `文件夹名·会话短id`(如 `opt·2a6472`)。想要看得懂的名字:

- **给项目目录放个 `.cctl-name` 文件**(内容就是名字)→ 该目录所有会话都用这名字,已在跑的下次动作即生效。
- 或**启动时带环境变量**:`CCTL_NAME=后端 claude` → 这个窗口叫「后端」。

优先级 `CCTL_NAME` > `.cctl-name` > 文件夹名。**一旦有自定义名,那串 hex 短 id 自动隐藏。**

### 模型 · token(自动)

每行副标题的 `模型 · N tok` 在会话答完(`Stop`)时从该会话 transcript 累加得出(含 cache token,与官方 `/usage` 口径一致的累计值)。无需配置。

### 5h / weekly 限额条(可选,需订阅版)

顶部两条额度进度条是**真实数据**,但只有 Claude.ai **Pro/Max 订阅**才由服务端下发(hook 拿不到,只能从 statusLine 抓)。开启:

```bash
python3 /opt/claude-traffic-light/install.py --with-limits
```
它会把你现有的 statusLine 包一层(透传,不影响原状态栏),把 `rate_limits` 抽进 `~/.claude/traffic_status/ratelimits.json`。**下个会话产生第一次响应后**该文件才出现,widget 随即显示两条条;**拿不到就自动不显示(绝不显示假条)**。验证:`cat ~/.claude/traffic_status/ratelimits.json`,`five_used`/`week_used` 非 null 即成。

## 使用

- 左键拖动挪位置(记忆,下次开在原地);右键关闭。
- 想开机自启:把 `start_widget.cmd` 的快捷方式丢进 `shell:startup`。
- 可调项都在 `traffic_widget.py` 顶部常量(刷新间隔、颜色、TTL、宽度、名字长度上限)。

## 卸载

```bash
python3 /opt/claude-traffic-light/uninstall.py   # 只移除本工具的 hook,保留其它
```
Windows 侧的 `claude-traffic-widget` 文件夹自行删除。

## License

MIT —— 见 [`LICENSE`](./LICENSE)(保留原作者 `Copyright (c) 2026 weilizhe8` + 本 fork 修改版权)。
