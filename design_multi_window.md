# 多窗口支持设计脚本

## 问题分析

当前架构：多个 Claude 窗口共享一个 `traffic_status.json`，后写覆盖前写。

| 场景 | 问题 |
|------|------|
| 窗口A等确认(红)，窗口B在运行(黄) | B的PostToolUse写入"running"覆盖A的红色 |
| 窗口A完成(finished→idle)，窗口B仍在运行 | A的Stop写入"finished"，5秒后变idle，但B还在跑 |
| `tasklist`检测 | 只看有没有claude.exe，不知道有几个实例 |

## 设计方案

### 核心思路：每个 Claude 实例一个槽位，widget 聚合求最高优先级

```
每个 Claude 实例 = 一个 slot (以 PID 标识)
widget 读取所有 slot → 取最高优先级显示
slot 在 Stop 时清除，超时 (30s) 自动清理
```

优先级：`needs_confirmation` > `running` > `finished` > `idle`

### 状态文件改为目录结构

```
~/.claude/traffic_status/
  34180.json    ← PID 34180 的状态 {"status":"running",  "ts":1717000000}
  40228.json    ← PID 40228 的状态 {"status":"needs_confirmation", "ts":1717000001}
  40592.json    ← PID 40592 的状态 {"status":"idle", "ts":1717000002}
```

### 变更清单

#### 1. `traffic-update.cmd` — 写入改为按 PID 分片

当前：
```cmd
echo {"status":"%~1"} > "%USERPROFILE%\.claude\traffic_status.json"
```

改为（新文件 `traffic-update.cmd`，或新增 `.claude/hooks/traffic-update.sh`）：
- 获取当前进程的 PID（或父进程 claude.exe 的 PID）
- 写入 `~/.claude/traffic_status/<PID>.json`
- 内容带时间戳：`{"status":"running","ts":timestamp}`

**获取 PID 的方式**：hook 脚本通过 `$PPID`（bash）或父进程链找到 claude.exe 的 PID。或者在 settings.json 的 hook 命令中想办法传入。

**更实际的方案**：hook 命令无法直接获取 Claude 的 PID。替代方案是用一个唯一标识：
- 选项 A：hook 执行时用 `%RANDOM%` + 时间戳生成一个 session-id，写入 `session-<random>.json`，Stop 时删掉
- 选项 B：利用 Claude 可能暴露的环境变量（需确认有没有 `CLAUDE_SESSION_ID` 之类）

**推荐选项 A**，因为可控且不依赖 Claude 是否有环境变量。

#### 2. `traffic_light.py` — 聚合读取多 slot

改动点：
- `_read_status()` 改为遍历 `traffic_status/` 目录下所有 `.json` 文件
- 30 秒未更新的 slot 视为过期，删除文件
- 无有效 slot 时（Claude 全关了 / 过期了）= idle
- 有 slot 时取最高优先级显示
- 辅助文本从 "Running" 改为 "Running (2)" 表示有 2 个活跃窗口

优先级映射：
```python
PRIORITY = {"needs_confirmation": 3, "running": 2, "finished": 1, "idle": 0}
```

#### 3. `settings.json` hooks — 更新命令路径（已修复为绝对路径）

### 保留的逻辑
- `_claude_running()` 检测仍然保留作为兜底：如果所有 slot 都过期且 `tasklist` 无 claude.exe，强制 idle
- 闪烁逻辑不变
- finished TTL (5s) 逻辑移入每个 slot 自身（可选），或保留在 widget 聚合层

### 边界情况

| 情况 | 处理 |
|------|------|
| 手动杀进程，没执行 Stop hook | slot 30 秒过期自动清理 |
| 同一 PID 复用（进程重启后 PID 相同） | 时间戳会更新，不影响 |
| 窗口很多（10+） | 都是小 JSON 文件，遍历 < 1ms |
| 没有写权限 | 和现在一样，静默降级到进程检测 |
| 旧版只有 traffic_status.json | 向后兼容：如果读到旧版单文件，按原逻辑处理 |

### 不做的事
- 不改变 widget UI（仍然是三个灯）
- 不增加新依赖
- 不需要管理界面
