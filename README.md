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

- **每会话一行**:会话名 + 状态 + 距上次活动,状态点 🔵运行中 / 🟢已完成·空闲 / 🟡待确认(闪烁);会话名自动采用 **Claude 自己起的名字**(它写进终端标题的那个任务摘要),也可 ✎ 手动改
- **子代理/后台任务感知**:派发 subagent 时显示"派N个子代理中";主回合结束但后台 agent 或**后台 shell** 还在跑时显示"后台任务中",**不会误报已完成**(实时对照 Claude Code 自己的 busy/idle 状态)
- **闪烁提醒 + 点击确认**:已完成/待确认的行会闪,点圆点或标题 = "我知道了"停闪;你直接继续对话也自动停闪
- **真实限额条**(可选,Pro/Max):5h + weekly 剩余百分比与重置倒计时,数据来自 Anthropic 服务端下发,**绝不估算、拿不到就不显示**;快照 10 分钟节流,⟳ 按钮手动刷新
- **模型 · token**:从会话 transcript 自动累加(含 cache,与官方 `/usage` 口径一致的累计值)
- **终端 tab 自动改名**:hook 顺手把终端标题写成 `🔵 项目名`(状态实时变),"Ubuntu" 匿名 tab 一眼可认;面板里 ✎ 改名也会**即时同步到 tab 标题**;点面板行标题可跳转到对应终端窗口(`CCTL_NO_TITLE=1` 可关)。⚠️ 需要用能透传应用标题的方式进 WSL,见[「终端 tab 标题:怎么进 WSL 很重要」](#终端-tab-标题怎么进-wsl-很重要)
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
| **点行标题旁的 ✎(或双击标题)** | 给这个**会话**改显示名(只对当前会话生效;回车保存,清空回车=还原,Esc 取消);终端 tab 标题即时同步 |
| **点某行标题** | 已读 + **跳转到对应终端窗口**(按标题匹配,只认终端/编辑器进程;多 tab 同窗只能提窗、切不了 tab) |
| **点某行圆点** | 只确认"已完成/待确认"的闪烁提醒(已读停闪) |
| 右边缘拖拽 | 改宽度 |
| 底边(含右下角)拖拽 | 整体**等比例缩放**(0.6x–1.6x) |
| **Ctrl + 滚轮** | 整体缩放(同上) |
| 右键(任意位置) | 弹出菜单(刷新/收起/关闭) |

标题**不截断**:遇到长会话名窗口自动加宽;高度始终随行数自适应。

## 状态映射(hook → 面板)

| Claude Code 事件 | 面板状态 |
|---|---|
| `SessionStart` | ⚪ 空闲(`source=compact` 上下文压缩时不重置) |
| `UserPromptSubmit` | 🔵 运行中 |
| `SubagentStart/Stop` | 🔵 派N个子代理中(计数±1;主回合 Stop 时计数>0 则**保持运行中**) |
| `Notification`(`permission_prompt`) | 🟡 待确认(闪烁) |
| `PostToolUse`(节流) | 🔵 运行中(批准确认后翻回;兼作心跳) |
| `Stop`(无存活子代理) | 🟢 已完成(闪烁至你点击确认) |
| `Stop` 后 Claude 仍在忙(**后台 shell 没跑完**) | 🔵 后台任务中(widget 实时对照 `~/.claude/sessions/` 里 Claude 自己的 busy/idle,跑完自动转已完成) |
| `SessionEnd` | 移除该行 |

> 开着 `defaultMode: auto` 时权限提示极少,"待确认"基本不亮属正常;日常就是 运行中/已完成/空闲 三态。

## 会话命名(优先级从高到低)

1. widget 里点 ✎(或**双击行标题**)直接改——**只对当前这个会话生效**,会话结束即失效;改完会顺手把该会话的终端 tab 标题也刷成新名字
2. 启动时环境变量:`CCTL_NAME=后端 claude`
3. 项目目录放 `.cctl-name` 文件(内容即名字)
4. **Claude 自己起的会话名**(自动):Claude Code 会按当前任务给会话生成一个名字(就是它写进终端标题的那个,如 `fix-rename-sync`),hook 从 `~/.claude/sessions/` 读出来直接用——什么都不配,行名就已经是"这个会话在干嘛"
5. 都没有才落到 `目录名·会话短id`

2/3 是持久命名(跨会话生效);1 是临时的会话级别名,**不会**波及同目录的其它/新会话——想要"这个目录以后都叫 X",用 `.cctl-name`。1/2/3/4 显示时都自动隐藏 hex 短 id。

## 终端 tab 标题:怎么进 WSL 很重要

hook 会把 `🔵 会话名` 用 OSC 转义序列写进会话的 pts,状态一变 tab 标题跟着变;面板 ✎ 改名也即时同步过去;"点行标题跳转到对应终端"靠的同样是这个标题匹配。**但前提是终端愿意接受"应用标题"——这取决于你怎么进的 WSL**:

| 进入方式 | tab 标题 |
|---|---|
| ✅ **PowerShell tab 里敲 `wsl` 进入**(推荐) | 应用标题正常透传,自动改名/同步改名/跳转全部生效 |
| ✅ 自定义 WT profile,`commandline` 填 `wsl.exe -d Ubuntu --cd ~` | 同上(本质就是 wsl.exe 直启) |
| ❌ Windows Terminal 自带的 **Ubuntu profile** 直开 | Store 版 WSL 把标题强制钉成 "Ubuntu",应用标题被压死([WSL#8701](https://github.com/microsoft/WSL/issues/8701)),一切标题功能无效 |
| ❌ 手动右键**重命名过**的 tab | WT 会永久锁死该 tab 的应用标题(新开 tab 恢复) |

一句话:**别点 Ubuntu 图标,开个 PowerShell 敲 `wsl`**(或建一个 `wsl.exe` 的自定义 profile 设为默认)。另外 Claude Code 自己也会往标题里写任务摘要,和本工具写的是同一个名字、互不打架,只是本工具多带一个状态圆点。反向同步(tab 上手动改名 → 面板)做不到——WT 没有读 tab 名的 API。不想要标题功能:`CCTL_NO_TITLE=1`。

## 限额条说明

- 数据来源:Claude Code **statusLine** stdin 里服务端下发的 `rate_limits`(仅 Claude.ai Pro/Max 订阅有);`--with-limits` 会把你现有 statusLine 命令包一层**透传**(原状态栏不受影响),顺手抄 4 个字段落地
- **没有任何额外网络请求**;拿不到数据(非订阅/会话未产生响应)就**自动隐藏**,绝不显示估算的假条
- 验证:`cat ~/.claude/traffic_status/ratelimits.json`,`five_used`/`week_used` 非 null 即通

## 常见问题

- **行名显示 `opt·2a6472` 这种?** 那是兜底的"目录名·会话短id"——Claude 还没给这个会话生成名字(刚开的会话干一会儿就有了),等不及就双击标题手动改。
- **tab 标题一直是 "Ubuntu" 不变?** 你是从 WT 的 Ubuntu profile 直开的——见上文[「终端 tab 标题:怎么进 WSL 很重要」](#终端-tab-标题怎么进-wsl-很重要),换成 PowerShell 里敲 `wsl` 进入即可。
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
