# API Mock Server

> 本地大模型接口模拟服务器 — 用于测试 API 中转平台的请求转发和伪装功能

---

## 项目构建

本项目采用 **Vibe Coding** 方式构建，全程由 AI 辅助编程完成。

| 角色 | 工具 |
|------|------|
| 编程工具 | [Claude Code](https://github.com/anthropics/claude-code) / [OpenCode](https://github.com/opencode-ai/opencode) |
| 大模型 | Qwen3.6-PLUS / 小米 MiMo-v2-Pro |

---

## 项目描述

这是一个本地 Mock 服务器工具，用于测试大模型 API 中转平台的以下功能：

1. **请求转发验证** — 确认中转平台能正确将请求转发到上游 API 供应商
2. **响应转发验证** — 确认 thinking（推理过程）和结论内容都能正常返回
3. **UA 伪装验证** — 确认请求头的 User-Agent 字段已被正确覆盖为伪装值（如 Claude Code 或 OpenCode）

服务器提供两个兼容接口：
- **OpenAI 格式** — 模拟 `gpt-4` 等模型的响应
- **Anthropic 格式** — 模拟 `claude` 系列模型的响应（含 thinking 块）

---

## 安装与使用

### 方式一：直接使用打包好的 exe（推荐）

1. 双击运行 `dist/API-Mock-Server.exe`
2. 程序会自动启动 HTTP 服务和图形界面
3. 默认监听地址：`http://localhost:12312`

### 方式二：从源码运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动
python main.py
```

### 方式三：重新打包 exe

```bash
# Windows 下运行批处理脚本
build.bat
```

### 接口调用示例

**OpenAI 接口：**
```bash
curl -X POST http://localhost:12312/openai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-mock-abc123def456ghi789" \
  -d '{"model": "gpt-4", "messages": [{"role": "user", "content": "hello"}]}'
```

**Anthropic 接口：**
```bash
curl -X POST http://localhost:12312/anthropic/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: sk-mock-abc123def456ghi789" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model": "claude-sonnet-4-20250514", "messages": [{"role": "user", "content": "hello"}], "max_tokens": 1024}'
```

**流式请求：** 在请求体中添加 `"stream": true` 即可启用流式响应。

### GUI 功能说明

| 功能区域 | 说明 |
|----------|------|
| 接口信息面板 | 显示接口地址和 API Key，每行附带"复制"按钮 |
| 请求日志列表 | 自动刷新（每2秒），显示时间、类型、模型、客户端IP、UA、路径 |
| 请求详情 | 选中某条日志后，在下方展示完整的 Headers 和 Body |
| 服务器配置 | 修改监听端口、API Key，点击"重启服务器"生效 |
| 响应内容 | 编辑 OpenAI/Anthropic 的 thinking 和结论文本，点击"应用"生效 |
| 延迟模拟 | 设置 0~10 秒的响应延迟，模拟真实上游 API |
| 错误注入 | 配置 0%~100% 的错误概率和状态码，测试中转平台的错误处理 |
| 日志导出 | 支持导出为 JSON 或 CSV 文件 |

---

## 文件结构与技术架构

### 文件结构

```
API-TEST/
├── main.py                  # 主入口：Flask 服务器 + tkinter GUI（合并版）
├── mock_server.py           # 独立服务器模块（可单独使用）
├── mock_server_gui.py       # 独立 GUI 模块
├── requirements.txt         # Python 依赖
├── build.bat                # Windows 一键打包脚本
├── API-Mock-Server.spec     # PyInstaller 构建配置
├── dist/
│   └── API-Mock-Server.exe  # 打包好的可执行文件
└── README.md                # 本文件
```

### 技术架构

```
┌─────────────────────────────────────────────────────┐
│                   Windows GUI (tkinter)             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ 接口信息  │  │ 日志列表  │  │ 配置面板  │          │
│  └──────────┘  └──────────┘  └──────────┘          │
│                        │                            │
│                  Config（共享配置）                    │
│                        │                            │
├────────────────────────┼────────────────────────────┤
│              Flask HTTP Server                       │
│                        │                            │
│     ┌──────────────────┼──────────────────┐         │
│     │                  │                  │         │
│  /openai/...      /anthropic/...      /logs         │
│     │                  │                  │         │
│     ▼                  ▼                  ▼         │
│  记录日志 → 错误注入 → 延迟模拟 → 返回响应            │
└─────────────────────────────────────────────────────┘
```

**技术栈：**
- **Web 框架**: Flask 3.x
- **GUI 框架**: tkinter（Python 内置）
- **打包工具**: PyInstaller 6.x
- **运行环境**: Python 3.13+

---

## 业务逻辑

### 请求处理流程

```
客户端请求
    │
    ▼
┌─────────────────────┐
│  路由匹配            │
│  /openai 或 /anthropic│
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  1. 记录请求日志      │  保存时间、路径、模型、IP、UA、完整Headers、Body
│     到内存列表        │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  2. 错误注入判断      │  根据 error_rate 配置的概率，随机决定是否返回错误
│                      │  若命中，直接返回配置的 HTTP 状态码和错误信息
└────────┬────────────┘
         │ (未命中错误)
         ▼
┌─────────────────────┐
│  3. 延迟等待         │  根据 response_delay 配置，sleep 指定秒数
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  4. 判断是否流式      │  检查请求体中的 stream 字段
│                      │
│  ┌──────┬───────┐    │
│  │ 非流式│ 流式   │    │
│  │      │       │    │
│  │ 返回  │ SSE   │    │
│  │ JSON  │ 逐字  │    │
│  │       │ 推送   │    │
│  └──────┴───────┘    │
└─────────────────────┘
         │
         ▼
   返回响应给客户端
```

### OpenAI 接口响应格式

**非流式：**
```json
{
  "id": "chatcmpl-xxxx",
  "object": "chat.completion",
  "created": 1712345678,
  "model": "gpt-4",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "（配置的结论内容）",
      "reasoning_content": "（配置的 thinking 内容）"
    },
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 10, "completion_tokens": 50, "total_tokens": 60}
}
```

**流式（SSE）：** 先逐字推送 `reasoning_content`，再逐字推送 `content`，最后发送 `[DONE]`。

### Anthropic 接口响应格式

**非流式：**
```json
{
  "id": "msg_xxxx",
  "type": "message",
  "role": "assistant",
  "content": [
    {"type": "thinking", "thinking": "（配置的 thinking 内容）", "signature": "mock_signature_123"},
    {"type": "text", "text": "（配置的结论内容）"}
  ],
  "model": "claude-xxx",
  "stop_reason": "end_turn",
  "usage": {"input_tokens": 10, "output_tokens": 50}
}
```

**流式（SSE）：** 按 `message_start → content_block_start(thinking) → content_block_delta → content_block_stop → content_block_start(text) → content_block_delta → content_block_stop → message_delta → message_stop` 的事件顺序推送。

### 配置热更新

- **响应内容** — 修改后立即影响后续请求（无需重启）
- **延迟/错误注入** — 修改后立即影响后续请求（无需重启）
- **端口/API Key** — 需要点击"重启服务器"按钮生效

### 日志管理

- 所有请求日志存储在内存中，GUI 每 2 秒自动刷新
- 支持通过 API 查询（`GET /logs`）和清空（`POST /logs/clear`）
- 支持导出为 JSON（完整数据）或 CSV（关键字段）

---

## 许可证

本项目采用 [Apache-2.0 许可证](https://www.apache.org/licenses/LICENSE-2.0)。

```
Copyright 2026 cyfor

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

---

## 致谢

本项目依赖以下开源项目：

- [Flask](https://flask.palletsprojects.com/) — 轻量级 Python Web 框架（BSD-3-Clause）
- [PyInstaller](https://pyinstaller.org/) — Python 应用打包工具（GPL-2.0，仅用于构建）

---

## 联系方式

- **Email**: [cyfor@foxmail.com](mailto:cyfor@foxmail.com)
