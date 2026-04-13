# codex-scope

`codex-scope` 是一个面向 Codex 会话诊断的本地工具集。

它直接读取你机器上已经落盘的 Codex 数据：

- `~/.codex/sessions/**/*.jsonl`
- `~/.codex/state_*.sqlite`

目标很明确：

- 看清每次模型往返到底消耗了多少 token
- 看清当前会话真正送进模型的上下文内容
- 用一个实时悬浮窗监控最近往返、轮次分组和总量变化
- 生成可直接复制到新会话里的 AI 续聊卡

## 功能

- 精确 token 统计  
  读取 Codex 落盘的 `event_msg.token_count.info`，不是本地拍脑袋估算。

- 上下文回放  
  可以查看某次模型调用前，实际进入上下文池的内容。

- 实时监控窗口  
  可拖拽、置顶、中文界面，支持查看最近往返、按 `turn` 分组、点击柱子看上行/下行详情。

- AI 续聊卡  
  面向新会话机器输入，保留当前轮重点、文件痕迹和此前 session 脉络。

## 目录

- `codex_context_inspector.py`  
  会话扫描、上下文导出、精确 token 汇总。

- `codex_token_widget.py`  
  悬浮监控窗口。

- `codex_continue_summary.py`  
  AI 续聊卡窗口与续聊卡构建逻辑。

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

启动续聊卡窗口：

```bash
cd /Users/sean_1/codex/codex-tool
/opt/homebrew/bin/python3.13 codex_continue_summary.py
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

打印最新会话的续聊卡：

```bash
/opt/homebrew/bin/python3.13 codex_continue_summary.py --latest
```

## 说明

- 这个项目分析的是 Codex 本地持久化数据，不是网络抓包层的原始 websocket frame。
- 监控窗口展示的是“真实已发生的请求”。
- 续聊卡是给新会话继续任务用的机器输入，不会直接改写当前 Codex 内部上下文。
- 悬浮窗位置和一些状态会记录在 `~/.codex/codex_token_widget.json`。

## 下一步方向

- 继续打磨监控界面的可读性
- 继续打磨 AI 续聊卡的压缩质量
