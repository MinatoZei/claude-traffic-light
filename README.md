# 🚦 Claude Traffic Light — Claude Code 桌面会话面板

> A frameless always-on-top desktop panel that shows every Claude Code session's live status (running / done / waiting), subagent count, model·tokens, and your real 5h & weekly rate-limit bars. Built for WSL2 → Windows.

在 **Windows 桌面**挂一个无边框置顶小面板,一眼看到你在 **WSL 里跑的每个 Claude Code 会话**:谁在跑、谁跑完了、谁在等你确认、派了几个子代理、用的什么模型烧了多少 token,顶部还有**真实的 5h / 周限额进度条**。多开项目时不用再挨个切窗口看。

```
Claude limits                      ⟳ ▼ ✕
5h left 79%                        1h50m
██████████████████████████░░░░░░
weekly left 92%                    4d19h
██████████████████████████████░░
──────────────────────────────────────
🔵 后端                              4s
   派3个子代理中 · fable-5 · 48M tok
🟢 RuoYi-Vue3·a465                  12s
   已完成 · sonnet-5 · 26M tok
🟡 爬虫                              1m
   待确认 · haiku-4-5 · 1M tok
```

## 特性

- **每会话一行**:项目名(可自定义)+ 状态 + 距上次活动,状态点 🔵运行中 / 🟢已完成·空闲 / 🟡待确认(闪烁)
- **子代理感知**:派发 subagent 时显示"派N个子代理中";主回合结束但后台 agent 还在跑时**不会误报已完成**
- **闪烁提醒 + 点击确认**:已完成/待确认的行会闪,点圆点或标题 = "我知道了"停闪;你直接继续对话也自动停闪
- **真实限额条**(可选,Pro/Max):5h + weekly 剩余百分比与重置倒计时,数据来自 Anthropic 服务端下发,**绝不估算、拿不到就不显示**;快照 10 分钟节流,⟳ 按钮手动刷新
- **模型 · token**:从会话 transcript 自动累加(含 cache,与官方 `/usage` 口径一致的累计值)
- **终端 tab 自动改名**:hook 顺手把终端标题写成 `🔵 项目名`(状态实时变),"Ubuntu" 匿名 tab 一眼可认;点面板行标题可跳转到对应终端窗口(`CCTL_NO_TITLE=1` 可关)
- **零网络请求**:全部数据来自本地文件与 Claude Code 自带的 hook/statusLine 通道
- **窗口体验**:铁置顶(真 `HWND_TOPMOST`)、拖动、▼ 收起成一条(显示 N会话·N运行·N空闲 汇总)、右下角拖拽改宽、Ctrl+滚轮整体缩放、✕ 关闭;位置/宽度/缩放/收起/已读全部记忆
- **零第三方依赖**:两端都是 Python 标准库(tkinter)+ bash + jq

## 架构

```
WSL (Ubuntu)                                Windows 桌面
Claude Code 会话
   │  生命周期 hook(stdin JSON)
   ▼
traffic_hook.py ──写──► ~/.claude/traffic_status/<session_id>.json
statusline-ratelimit.sh ──写──► ratelimits.json(限额,10min 节流)
                                 │  \\wsl.localhost\<distro>\...\traffic_status\
                                 ▼
                        traffic_widget.py(pythonw + tkinter,置顶悬浮)
```

两端只靠文件解耦:hook 只管写状态,widget 只管读+显示。不开端口、无常驻服务、任一端崩了不影响另一端。

## 系统要求

- Windows 10/11 + WSL2(发行版任意,默认按 Ubuntu 生成路径)
- WSL 内:Python 3、jq(限额条需要,`apt install jq`)
- Windows 侧:Python 3(python.org 官方安装包,自带 tkinter;**不要用 Microsoft Store 版**)

## 安装

> 🤖 **让 AI 装**:直接把本仓库丢给 Claude Code 说"照 CLAUDE.md 装一下",[CLAUDE.md](./CLAUDE.md) 里有给 AI 看的完整安装/验证/排障手册。

手动三步:

```bash
# 1. WSL 里 clone
git clone https://github.com/MinatoZei/claude-traffic-light /opt/claude-traffic-light

# 2. 安装(合并 hook 进 ~/.claude/settings.json + 部署 widget 到 Windows)
python3 /opt/claude-traffic-light/install.py
#    要限额条(Pro/Max 订阅)就加 --with-limits:
python3 /opt/claude-traffic-light/install.py --with-limits
```

3. Windows 装好 Python 后,双击 `C:\Users\<你>\claude-traffic-widget\start_widget.cmd` 启动(无黑框,且已自动注册开机自启)。**重启你的 Claude Code 会话**让 hook 生效。

install 是幂等的:反复运行不会叠加;它**只 append 不覆盖**你 settings.json 里已有的 hooks/statusLine(先自动备份成 `settings.json.bak-<时间戳>`)。

## 操作手势

| 操作 | 效果 |
|---|---|
| 左键拖(任意空白处) | 移动窗口(位置记忆) |
| **✕**(右上) | 关闭 |
| **▼ / 双击标题栏** | 收起成一条细标题,显示 `N会话 · N运行 · N完成 · N空闲` 汇总;再点展开 |
| **⟳** | 手动刷新限额快照(平时 10 分钟自动一次) |
| **点行标题旁的 ✎(或双击标题)** | 给这个项目改显示名(回车保存,清空回车=还原,Esc 取消) |
| **点某行标题** | 已读 + **跳转到对应终端窗口**(按标题匹配,只认终端/编辑器进程;多 tab 同窗只能提窗、切不了 tab) |
| **点某行圆点** | 只确认"已完成/待确认"的闪烁提醒(已读停闪) |
| 右下角拖拽角 | 自由改宽度 |
| **Ctrl + 滚轮** | 整体缩放(0.6x–1.6x) |
| 右键(任意位置) | 退出 |

## 状态映射(hook → 面板)

| Claude Code 事件 | 面板状态 |
|---|---|
| `SessionStart` | ⚪ 空闲(`source=compact` 上下文压缩时不重置) |
| `UserPromptSubmit` | 🔵 运行中 |
| `SubagentStart/Stop` | 🔵 派N个子代理中(计数±1;主回合 Stop 时计数>0 则**保持运行中**) |
| `Notification`(`permission_prompt`) | 🟡 待确认(闪烁) |
| `PostToolUse`(节流) | 🔵 运行中(批准确认后翻回;兼作心跳) |
| `Stop`(无存活子代理) | 🟢 已完成(闪烁至你点击确认) |
| `SessionEnd` | 移除该行 |

> 开着 `defaultMode: auto` 时权限提示极少,"待确认"基本不亮属正常;日常就是 运行中/已完成/空闲 三态。

## 会话命名(三选一,优先级从高到低)

1. 启动时环境变量:`CCTL_NAME=后端 claude`
2. 项目目录放 `.cctl-name` 文件(内容即名字)
3. widget 里**双击行标题**直接改(存在面板侧,跨会话生效)

前两种是"会话级"命名(hex 短 id 自动隐藏);第三种是"项目级"别名(保留短 id 以区分同目录多开)。

## 限额条说明

- 数据来源:Claude Code **statusLine** stdin 里服务端下发的 `rate_limits`(仅 Claude.ai Pro/Max 订阅有);`--with-limits` 会把你现有 statusLine 命令包一层**透传**(原状态栏不受影响),顺手抄 4 个字段落地
- **没有任何额外网络请求**;拿不到数据(非订阅/会话未产生响应)就**自动隐藏**,绝不显示估算的假条
- 验证:`cat ~/.claude/traffic_status/ratelimits.json`,`five_used`/`week_used` 非 null 即通

## 常见问题

- **行名显示 `opt·2a6472` 这种?** 那是"目录名·会话短id",双击标题改名即可。
- **状态不更新/功能缺失?** widget 是启动时加载代码的,更新后要**重启 widget**;hook 集合是**会话启动时**定死的,装完 hook 后老会话要重启才上报(`claude -c` 可续上下文)。
- **"待确认"从来不亮?** 你开了自动批准(auto mode),属正常。
- **多显示器/发行版不是 Ubuntu?** 启动脚本里 `CLAUDE_TRAFFIC_DIR` 改成你的 `\\wsl.localhost\<发行版>\<home>\.claude\traffic_status`。
- **纯 Linux 桌面能用吗?** 能,widget 在 WSLg/Linux 下直接 `python3 traffic_widget.py`(读本地 `~/.claude/traffic_status`),但置顶压不住原生 Windows 窗口。

## 卸载

```bash
python3 /opt/claude-traffic-light/uninstall.py   # 移除本工具的 hook + 还原 statusLine,其它一概不动
```
Windows 侧删掉 `claude-traffic-widget` 文件夹和启动项 `shell:startup` 里的 `claude-traffic-widget.vbs`。

## 来源与致谢 · Attribution

**Forked from [weilizhe8-del/claude-code-traffic-light](https://github.com/weilizhe8-del/claude-code-traffic-light) (MIT).** This is a heavily modified version:原版是 Windows 单聚合红绿灯(PowerShell hook);本 fork 改为 stdin 解析的 Python hook、每会话列表、子代理计数、限额条、确认机制等。原作者的多窗口设计文档保留在 [`design_multi_window.md`](./design_multi_window.md)。

## License

MIT — 见 [`LICENSE`](./LICENSE)(保留原作者版权声明 + 本 fork 修改版权)。
