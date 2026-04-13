# Codex Context Inspector

这个小工具直接读取本机 Codex 已经落盘的数据：

- `~/.codex/sessions/**/*.jsonl`
- `~/.codex/state_*.sqlite`

它能做两件事：

1. 看每一次模型调用之前，Codex 本地持久化下来的上下文内容。
2. 统计精确 token。
3. 用一个可拖拽的小悬浮窗监控最新请求、今日总量、全部总量和请求图表。

“精确”的来源不是本地估算，而是 Codex 会话文件里的 `event_msg.token_count.info`：

- 单次模型调用：取 `last_token_usage`
- 整个 session：取最后一次 `total_token_usage.total_tokens`
- 如果某个 session 还没来得及把最后值刷到 sqlite，就优先用 JSONL 里的最新值

## 快速开始

```bash
cd /Users/sean_1/codex/codex-tool
python3 codex_context_inspector.py summary --latest
```

启动悬浮窗：

```bash
cd /Users/sean_1/codex/codex-tool
python3 codex_token_widget.py
```

macOS 双击启动：

在 Finder 里直接双击：

`/Users/sean_1/codex/codex-tool/启动 Codex Token 监控.command`

## 常用命令

列出最近 session：

```bash
python3 codex_context_inspector.py sessions --limit 10
```

统计所有 session 的总 token：

```bash
python3 codex_context_inspector.py totals --exact
```

查看某个 session 每次模型调用的 token 消耗：

```bash
python3 codex_context_inspector.py calls --latest
```

查看第 1 次模型调用时，真正送进上下文的内容：

```bash
python3 codex_context_inspector.py dump-context --latest --call 1 --max-chars 1000
```

导出 JSON：

```bash
python3 codex_context_inspector.py dump-context --latest --call 1 --json
```

指定某个 thread：

```bash
python3 codex_context_inspector.py summary --thread-id 019d8274-871d-7fa1-a0b0-d31316bce63c
```

调整悬浮窗刷新频率：

```bash
python3 codex_token_widget.py --refresh-ms 3000
```

模拟 Phase 1 上下文节流后的 token 节省：

```bash
python3 codex_context_throttler.py --latest
```

模拟某一次具体请求：

```bash
python3 codex_context_throttler.py --latest --call 3
```

导出节流模拟 JSON：

```bash
python3 codex_context_throttler.py --latest --json
```

设置阈值，只有达到指定 `K` 才输出模拟结果：

```bash
python3 codex_context_throttler.py simulate --latest --threshold-k 120
```

自动轮询，达到阈值后自动运行：

```bash
python3 codex_context_throttler.py watch --threshold-k 120
```

调整自动轮询间隔：

```bash
python3 codex_context_throttler.py watch --threshold-k 120 --interval-sec 3
```

## 说明

- 这个工具看到的是 Codex 本地持久化下来的上下文，不是抓包层的原始 websocket frame。
- 对“我这一轮到底带了哪些提示词、开发者消息、用户消息、工具输出”这种问题，它已经够用了。
- 如果你后面还想看网络层原始请求体，我可以再帮你补一个本地代理版。
- 悬浮窗会记住上次拖拽后的窗口位置，状态文件在 `~/.codex/codex_token_widget.json`。
