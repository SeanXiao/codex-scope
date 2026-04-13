# codex-scope

`codex-scope` 是一个面向 Codex 会话诊断的本地工具集。

它直接读取你机器上已经落盘的 Codex 数据：

- `~/.codex/sessions/**/*.jsonl`
- `~/.codex/state_*.sqlite`

目标很明确：

- 看清每次模型往返到底消耗了多少 token
- 看清当前会话真正送进模型的上下文内容
- 用一个实时悬浮窗监控最近往返、轮次分组和总量变化
- 在本地模拟“如果做上下文节流，大概能省多少 token”

## 功能

- 精确 token 统计  
  读取 Codex 落盘的 `event_msg.token_count.info`，不是本地拍脑袋估算。

- 上下文回放  
  可以查看某次模型调用前，实际进入上下文池的内容。

- 实时监控窗口  
  可拖拽、置顶、中文界面，支持查看最近往返、按 `turn` 分组、点击柱子看上行/下行详情。

- 节流模拟器  
  本地模拟 Phase 1 上下文压缩策略，估算理论可节省的输入 token。

## 目录

- `codex_context_inspector.py`  
  会话扫描、上下文导出、精确 token 汇总。

- `codex_token_widget.py`  
  悬浮监控窗口。

- `codex_context_throttler.py`  
  节流模拟器 CLI。

- `codex_context_budget.py`  
  节流预算策略。

- `codex_context_memory.py`  
  工作记忆结构。

- `CODEX_CONTEXT_THROTTLING_PLAN.md`  
  上下文节流设计方案。

## 快速开始

查看最新会话摘要：

```bash
cd /Users/sean_1/codex/codex-tool
python3 codex_context_inspector.py summary --latest
```

启动监控窗口：

```bash
cd /Users/sean_1/codex/codex-tool
/opt/homebrew/bin/python3.13 codex_token_widget.py
```

macOS 双击启动：

- `启动 Codex Token 监控.command`
- `Codex Token 监控.app`

## 常用命令

列出最近会话：

```bash
python3 codex_context_inspector.py sessions --limit 10
```

统计全部 session 的精确总 token：

```bash
python3 codex_context_inspector.py totals --exact
```

查看最新 session 的每次调用：

```bash
python3 codex_context_inspector.py calls --latest
```

导出某次调用前的上下文：

```bash
python3 codex_context_inspector.py dump-context --latest --call 1 --max-chars 1000
```

导出 JSON：

```bash
python3 codex_context_inspector.py dump-context --latest --call 1 --json
```

运行节流模拟：

```bash
python3 codex_context_throttler.py --latest
```

模拟某次具体调用：

```bash
python3 codex_context_throttler.py --latest --call 3
```

输出 JSON：

```bash
python3 codex_context_throttler.py --latest --json
```

达到阈值时才输出模拟结果：

```bash
python3 codex_context_throttler.py simulate --latest --threshold-k 120
```

## 说明

- 这个项目分析的是 Codex 本地持久化数据，不是网络抓包层的原始 websocket frame。
- 监控窗口展示的是“真实已发生的请求”。
- 节流模拟器给的是“理论可压缩空间”，不会直接改写 Codex 内部上下文。
- 悬浮窗位置和一些状态会记录在 `~/.codex/codex_token_widget.json`。

## 下一步方向

- 更细的工具输出归因
- 更稳定的 turn 级压缩摘要
- 更完整的 harness / context planner 实验
