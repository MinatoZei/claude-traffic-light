# CLAUDE.md — AI 安装/维护手册

你(AI 助手)被要求在用户机器上安装或维护本工具。本文件是给你的完整执行手册。按顺序做,每步都有验证命令;任何一步失败先停下报告,不要瞎猜。

## 这是什么

Claude Code 桌面会话面板:WSL 里的 hook 把每个会话的状态写成小 JSON 文件,Windows 侧的 tkinter 悬浮窗读这些文件渲染。两端只靠文件解耦。详见 README.md。

组件:
- `traffic_hook.py` — 挂在 Claude Code hooks 上,读 stdin JSON 写 `~/.claude/traffic_status/<session_id>.json`
- `traffic_widget.py` — Windows 侧悬浮窗(也可在 Linux 桌面直接跑)
- `statusline-ratelimit.sh` — statusLine 包装,抓真实 5h/weekly 限额(可选)
- `install.py` / `uninstall.py` — 幂等安装/卸载

## 安装步骤(在 WSL 内执行)

### 0. 前置检查

```bash
python3 --version            # 需要 Python 3.8+
which jq                     # 限额条需要;没有则 apt install -y jq(或跳过 --with-limits)
ls ~/.claude/settings.json   # Claude Code 已初始化
echo $WSL_DISTRO_NAME        # 记下发行版名,后面核对 UNC 路径
```

### 1. 运行安装

```bash
python3 <本仓库路径>/install.py                # 基础:hooks + widget 部署
python3 <本仓库路径>/install.py --with-limits  # 用户是 Pro/Max 订阅且想要限额条时用这个
```

预期输出包含:`[hooks] merged into ...`、`[widget] deployed -> /mnt/c/Users/<用户>/claude-traffic-widget`、`[widget] pythonw: C:\...`(若显示 `pyw` 说明没找到 Windows Python,见排障)。

**关于 install 的行为,你需要知道**:
- 它**合并**(append)hook 进 `~/.claude/settings.json`,不覆盖已有 hooks;幂等靠命令里含 `traffic_hook.py` 这个 marker 去重;写入前自动备份 `settings.json.bak-<unixts>`
- `--with-limits` 会把现有 `statusLine.command` 存进 `~/.claude/traffic_status/__orig_statusline` 再替换为包装脚本(透传,原状态栏不受影响)
- 自动往 Windows 启动目录写 `claude-traffic-widget.vbs` 实现开机自启

### 2. 验证 hook(不需要真跑 Claude)

```bash
echo '{"session_id":"testX","cwd":"/tmp/demo","hook_event_name":"UserPromptSubmit"}' \
  | python3 <本仓库路径>/traffic_hook.py running
cat ~/.claude/traffic_status/testX.json   # 应含 "status": "running", "project": "demo"
echo '{"session_id":"testX","hook_event_name":"SessionEnd"}' \
  | python3 <本仓库路径>/traffic_hook.py end
ls ~/.claude/traffic_status/testX.json 2>/dev/null && echo "FAIL 应已删除" || echo "OK"
```

同时确认 settings.json 合并正确:

```bash
python3 -c "
import json,os
d=json.load(open(os.path.expanduser('~/.claude/settings.json')))
evs=['SessionStart','UserPromptSubmit','Notification','Stop','SubagentStart','SubagentStop','SessionEnd']
for ev in evs:
    n=sum(1 for g in d['hooks'].get(ev,[]) for h in g.get('hooks',[]) if 'traffic_hook.py' in h.get('command',''))
    print(ev, 'OK' if n==1 else f'BAD({n})')"
```

### 3. Windows 侧

用户需要在 Windows 装 Python(python.org 官方包,勾 *Add to PATH*,保留 tcl/tk;**不要**装 Microsoft Store 版)。装好后让用户双击 `C:\Users\<用户>\claude-traffic-widget\start_widget.cmd`。

你可以从 WSL 代为启动/检查:

```bash
# 启动(不要用 cmd.exe /c start,interop 可能挂住 shell;用 powershell Start-Process)
powershell.exe -NoProfile -Command "Start-Process -FilePath 'C:\Users\<用户>\claude-traffic-widget\start_widget.cmd' -WindowStyle Hidden"
# 确认实例(应恰好 1 个)
powershell.exe -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { \$_.CommandLine -like '*traffic_widget*' } | ForEach-Object { \$_.ProcessId }"
```

### 4. 收尾

告诉用户两件事:

1. **已开着的 Claude Code 会话要重启**(hook 集合在会话启动时定死;`claude -c` 可续上下文)。新会话自动生效。
2. **tab 标题功能(自动改名/✎ 同步/点击跳转)要求用能透传应用标题的方式进 WSL**:从 PowerShell tab 敲 `wsl` 进入,或建一个 `commandline: wsl.exe -d Ubuntu --cd ~` 的自定义 WT profile。从 WT 自带 Ubuntu profile 直开会被 Store WSL 强制锁标题 "Ubuntu"(WSL#8701),标题类功能全部无效(面板本身不受影响);手动右键改过名的 tab 也会永久锁死应用标题。详见 README「终端 tab 标题」一节。

限额条验证(装了 --with-limits 且有活跃会话后):

```bash
cat ~/.claude/traffic_status/ratelimits.json  # five_used/week_used 非 null 即通;全 null=非订阅账号,面板会自动隐藏限额条,属正常
```

## 排障速查

| 症状 | 原因/处理 |
|---|---|
| `[widget] pythonw: pyw` | Windows 没装 python.org 版 Python;装好后重跑 install.py |
| 双击 cmd 报"找不到 pythonw" | 同上;启动脚本用绝对路径,重跑 install.py 会重新探测 |
| 面板不更新/缺功能 | widget 进程跑的是旧代码:杀掉 pythonw 重启(见上面 powershell 命令,先 Stop-Process 再启动,防多实例叠窗) |
| 会话不上报 | 该会话早于 hook 安装启动,重启会话 |
| 限额条不出现 | 非 Pro/Max、或没加 --with-limits、或会话还没产生第一次响应 |
| 发行版不是 Ubuntu | 编辑 Windows 侧 start_widget.cmd 里的 `CLAUDE_TRAFFIC_DIR` UNC 路径(install.py 会按 $WSL_DISTRO_NAME 自动生成,一般不用手改) |

## 卸载

```bash
python3 <本仓库路径>/uninstall.py   # 按 marker 移除 hooks + 还原 statusLine,其它 hook 不动
```
再删 Windows 侧 `claude-traffic-widget` 文件夹和 `shell:startup` 里的 `claude-traffic-widget.vbs`。

## 改代码时的红线(维护者/AI 必读)

1. **hook 绝不能往 stdout 打印任何东西**——`SessionStart`/`UserPromptSubmit` 的 stdout 会被注入 Claude 上下文,污染对话。debug 走 stderr,异常吞掉,永远 exit 0。
2. **写状态文件必须原子**(写 `.tmp` 再 `os.replace`),widget 随时在读。
3. **不要挂 PreToolUse**(它在权限判定**之前**触发,会造成"假等待");`PostToolUse` 可以挂但**必须带节流**(已 running 且心跳 <25s 时跳过写盘、finished 不复活)——它是"用户批准确认后翻回运行中"的唯一信号,同时兼作 running 心跳。
4. `SessionStart` 收到 `source=="compact"` 必须直接 return(上下文压缩不是新会话,不能把 running 打回 idle)。
5. `Stop` 时若子代理计数>0(等后台 agent),**保持 running 不清零**;计数为 0 的 Stop 才是真完成。
6. `Notification` 必须按 `notification_type` 分流(`permission_prompt`→待确认,`idle_prompt`→空闲,其余忽略),不能一律当待确认。
7. install/uninstall 改 settings.json 必须:备份 → setdefault/append(不覆盖用户已有 hooks)→ marker 幂等去重 → 原子写回。
8. widget 里 `__` 前缀文件是内部状态(位置/别名/刷新标记),扫描 slot 时必须跳过;`ratelimits.json` 同理。
9. 限额数据拿不到就隐藏,**绝不显示估算的假进度条**。
10. tkinter 光标名/字体等平台差异要 try/except 回退(如 `size_nw_se` 是 Windows 专属)。
11. `__names` 别名表按 **sid** 键存(会话级),绝不能按 project 目录名键存——多个会话常共用同一目录,项目级别名会让一个改名污染同目录所有新会话。alias 只影响"显示 + tab 标题";slot 的 `project` 字段必须始终是真实目录名(stickiness 回填、跳转匹配都依赖它)。
12. slot 的 `auto` 字段(Claude 自动会话名)来自 `~/.claude/sessions/<claude进程pid>.json` 的 `name`,通过 /proc 祖先链定位(hook 是 claude 的子进程,祖先 pid 即文件名)。**必须校验文件里 `sessionId == sid`** 再采用(pid 会被复用,不校验会串到别人会话的名字);读不到就 sticky 用上一次的值,绝不为此报错。显示优先级固定:✎ alias > CCTL_NAME/.cctl-name > auto > 目录名·短id。
13. widget 经 wsl.exe 推 tab 标题必须:**用 `-e`(exec)不用 `--`**(`--` 模式下 `sh -c` 后面的位置参数全部丢失,`$1` 恒为空,实测 argc=0);**标题必须 base64 成纯 ASCII 过参**、Linux 侧 `base64 -d` 解回(wsl.exe 按 Windows 代码页转换 argv,中文 Windows=GBK,中文/emoji 直传会 mojibake,WT 直接丢弃非法 UTF-8 的 OSC)。两条都在真 wsl.exe 上验证过。
14. "后台任务中"判定:**后台 shell 跑完/没跑完不产生任何 hook 事件**,唯一信号是 sessions/<cpid>.json 的 `status` 字段(Claude 自己维护,busy/idle)。widget 每次轮询只对 slot 状态为 finished/idle 的行做**升级**(→ 运行中·后台任务中),绝不降级 needs_confirmation、绝不反向把 busy 当 finished;同样必须校验 sessionId;bg 行豁免 30min STALE 置灰(它每 2s 都被实时确认过)。
