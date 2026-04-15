# API Mock Server

> 本地大模型接口模拟服务器 v4.0 — 用于测试 API 中转平台的请求转发和伪装功能

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

v4.0 采用 **FastAPI + NiceGUI** 技术栈，双击 exe 后自动打开浏览器，提供现代化的 Web 管理界面。

---

## 安装与使用

### 方式一：直接使用打包好的 exe（推荐）

1. 双击运行 `dist/API-Mock-Server.exe`
2. 程序会自动启动 HTTP 服务并打开浏览器
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

双击 exe 后自动打开浏览器，访问 Web 管理界面。支持以下页面：

| 页面 | 说明 |
|------|------|
| 📊 仪表盘 | 总请求数、成功率、RPM、模型调用柱状图、最近请求表格 |
| 📝 日志详情 | 完整日志表格、搜索过滤、请求详情展开、导出 JSON/CSV |
| ⚙️ 服务器配置 | 端口、API Key、认证开关、响应内容编辑、延迟/错误注入、转发配置 |
| 🔌 端口管理 | 添加/删除额外监听端口 |
| ℹ️ 接口信息 | 接口地址展示、复制按钮、curl 调用示例 |

顶部栏支持深色/浅色主题一键切换。

---

## 文件结构与技术架构

### 文件结构

```
API-TEST/
├── main.py                  # 主入口：FastAPI 服务器 + NiceGUI Web 管理面板（v4.0）
├── mock_server.py           # 独立服务器模块（v1.0 遗留）
├── mock_server_gui.py       # 独立 GUI 模块（v1.0 遗留）
├── config.json              # [自动生] 持久化配置文件
├── logs/                    # [自动生成] 日志持久化目录
├── requirements.txt         # Python 依赖
├── build.bat                # Windows 一键打包脚本
├── API-Mock-Server.spec     # PyInstaller 构建配置
├── dist/
│   └── API-Mock-Server.exe  # 打包好的可执行文件（~46MB）
└── README.md                # 本文件
```

### 技术架构

```
┌─────────────────────────────────────────────────────┐
│              FastAPI + NiceGUI (同一端口)             │
│                                                     │
│  ┌─────────────────┐  ┌───────────────────────────┐ │
│  │   API 路由       │  │  NiceGUI Web 管理界面      │ │
│  │                 │  │  ┌──────┐ ┌──────┐ ┌────┐ │ │
│  │ /openai/...     │  │  │仪表盘 │ │ 日志  │ │配置│ │ │
│  │ /anthropic/...  │  │  └──────┘ └──────┘ └────┘ │ │
│  │ /logs /stats    │  │                           │ │
│  └────────┬────────┘  └───────────────────────────┘ │
│           │                                         │
│     记录日志 → 错误注入 → 延迟模拟 → 返回响应         │
└─────────────────────────────────────────────────────┘
```

**技术栈：**
- **Web 框架**: FastAPI（ASGI）
- **UI 框架**: NiceGUI（基于 FastAPI + Quasar/Vue）
- **打包工具**: PyInstaller 6.x
- **运行环境**: Python 3.13+

**v4.0 变更：**
- Flask → FastAPI（WSGI → ASGI）
- tkinter/CustomTkinter 桌面窗口 → NiceGUI 浏览器管理界面
- 支持 ECharts 图表、数据表格、多页面导航

**v2.1 新增特性：**
- 真实接口转发（Mock/转发模式 tab 切换，OpenAI/Anthropic 独立上游配置）
- 请求原样转发到上游 API，响应原样返回
- 日志新增"模式"列区分 mock/forward

**v2.0 新增特性：**
- API Key 鉴权验证（支持 OpenAI/Anthropic 两种认证方式）
- 日志搜索过滤、数量限制、持久化写入
- 配置自动保存到 `config.json`
- 响应 Token 数可自定义
- 多消息对话轮次响应
- 实时请求统计面板（含模型调用柱状图）
- 深色/浅色主题切换
- 多端口并发监听

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
- **端口** — 需要点击"保存"后重启服务生效

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

- [FastAPI](https://fastapi.tiangolo.com/) — 现代 Python Web 框架（MIT）
- [NiceGUI](https://nicegui.io/) — 基于 FastAPI + Quasar 的 Python Web UI（MIT）
- [Uvicorn](https://www.uvicorn.org/) — ASGI 服务器（BSD-3-Clause）
- [PyInstaller](https://pyinstaller.org/) — Python 应用打包工具（GPL-2.0，仅用于构建）

---

## 联系方式

- **Email**: [cyfor@foxmail.com](mailto:cyfor@foxmail.com)
