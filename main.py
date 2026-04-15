#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
API Mock Server 打包入口 - 合并GUI和Server为单个exe
"""

import os
import csv
import json
import random
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
from datetime import datetime

from flask import Flask, request, jsonify, Response

# ============================================================
# 全局配置
# ============================================================

class Config:
    """全局配置，GUI和Server共享"""
    port = 12312
    api_key = "sk-mock-abc123def456ghi789"
    response_thinking = "这是Mock服务器模拟的thinking过程。首先分析用户的问题，然后逐步推理得出结论。整个过程展示了thinking功能的转发是否正常。"
    response_content = "这是一个Mock服务器返回的固定结论内容。你的API中转平台转发功能正常！"
    response_thinking_anthropic = "这是Mock服务器模拟的thinking过程。Anthropic的thinking块展示了模型的推理过程，用于验证thinking功能是否正常转发。"
    response_content_anthropic = "这是一个Mock服务器返回的固定结论内容。你的API中转平台转发功能正常！Anthropic接口测试通过。"
    response_delay = 0.0  # 秒
    error_rate = 0  # 0-100, 错误注入概率
    error_code = 500  # 500/502/503/504
    error_message = "Internal Server Error"


# ============================================================
# Flask Server (内嵌)
# ============================================================

server_app = Flask(__name__)

request_logs = []
logs_lock = threading.Lock()


def add_log(entry):
    with logs_lock:
        request_logs.append(entry)


def get_logs():
    with logs_lock:
        return list(request_logs)


def clear_logs():
    global request_logs
    with logs_lock:
        request_logs = []


def maybe_inject_error():
    """根据配置的概率决定是否注入错误"""
    if Config.error_rate > 0 and random.randint(1, 100) <= Config.error_rate:
        return True
    return False


def apply_delay():
    """根据配置添加延迟"""
    if Config.response_delay > 0:
        time.sleep(Config.response_delay)


@server_app.route('/openai/v1/chat/completions', methods=['POST'])
def openai_chat_completions():
    from time import time as _time
    body = request.get_json(silent=True) or {}
    model = body.get('model', 'unknown')

    log_entry = {
        'id': str(uuid.uuid4())[:8],
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'method': request.method,
        'path': request.path,
        'model': model,
        'client_ip': request.remote_addr,
        'user_agent': request.headers.get('User-Agent', ''),
        'content_type': request.headers.get('Content-Type', ''),
        'auth_header': request.headers.get('Authorization', '')[:20] + '...' if request.headers.get('Authorization') else '',
        'headers': dict(request.headers),
        'body': body,
        'api_type': 'openai'
    }
    add_log(log_entry)

    # 错误注入
    if maybe_inject_error():
        return jsonify({
            'error': {
                'message': Config.error_message,
                'type': 'server_error',
                'code': Config.error_code
            }
        }), Config.error_code

    # 延迟
    apply_delay()

    response_data = {
        'id': f'chatcmpl-{uuid.uuid4().hex[:10]}',
        'object': 'chat.completion',
        'created': int(_time()),
        'model': model,
        'choices': [{
            'index': 0,
            'message': {
                'role': 'assistant',
                'content': Config.response_content,
                'reasoning_content': Config.response_thinking
            },
            'finish_reason': 'stop'
        }],
        'usage': {
            'prompt_tokens': 10,
            'completion_tokens': 50,
            'total_tokens': 60
        }
    }

    if body.get('stream', False):
        def generate():
            for char in Config.response_thinking:
                chunk = {
                    'id': f'chatcmpl-{uuid.uuid4().hex[:10]}',
                    'object': 'chat.completion.chunk',
                    'created': int(_time()),
                    'model': model,
                    'choices': [{'index': 0, 'delta': {'role': 'assistant', 'reasoning_content': char}, 'finish_reason': None}]
                }
                yield f'data: {json.dumps(chunk)}\n\n'
                time.sleep(0.01)

            for char in Config.response_content:
                chunk = {
                    'id': f'chatcmpl-{uuid.uuid4().hex[:10]}',
                    'object': 'chat.completion.chunk',
                    'created': int(_time()),
                    'model': model,
                    'choices': [{'index': 0, 'delta': {'content': char}, 'finish_reason': None}]
                }
                yield f'data: {json.dumps(chunk)}\n\n'
                time.sleep(0.01)

            chunk = {
                'id': f'chatcmpl-{uuid.uuid4().hex[:10]}',
                'object': 'chat.completion.chunk',
                'created': int(_time()),
                'model': model,
                'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]
            }
            yield f'data: {json.dumps(chunk)}\n\n'
            yield 'data: [DONE]\n\n'

        return Response(generate(), mimetype='text/event-stream')

    return jsonify(response_data)


@server_app.route('/anthropic/v1/messages', methods=['POST'])
def anthropic_messages():
    from time import time as _time
    body = request.get_json(silent=True) or {}
    model = body.get('model', 'unknown')

    log_entry = {
        'id': str(uuid.uuid4())[:8],
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'method': request.method,
        'path': request.path,
        'model': model,
        'client_ip': request.remote_addr,
        'user_agent': request.headers.get('User-Agent', ''),
        'content_type': request.headers.get('Content-Type', ''),
        'auth_header': request.headers.get('x-api-key', '')[:20] + '...' if request.headers.get('x-api-key') else '',
        'anthropic_version': request.headers.get('anthropic-version', ''),
        'headers': dict(request.headers),
        'body': body,
        'api_type': 'anthropic'
    }
    add_log(log_entry)

    # 错误注入
    if maybe_inject_error():
        return jsonify({
            'type': 'error',
            'error': {
                'type': 'api_error',
                'message': Config.error_message
            }
        }), Config.error_code

    # 延迟
    apply_delay()

    response_data = {
        'id': f'msg_{uuid.uuid4().hex[:12]}',
        'type': 'message',
        'role': 'assistant',
        'content': [
            {
                'type': 'thinking',
                'thinking': Config.response_thinking_anthropic,
                'signature': 'mock_signature_123'
            },
            {
                'type': 'text',
                'text': Config.response_content_anthropic
            }
        ],
        'model': model,
        'stop_reason': 'end_turn',
        'stop_sequence': None,
        'usage': {
            'input_tokens': 10,
            'output_tokens': 50,
            'cache_creation_input_tokens': 0,
            'cache_read_input_tokens': 0
        }
    }

    if body.get('stream', False):
        def generate():
            events = [
                {'type': 'message_start', 'message': {'id': response_data['id'], 'type': 'message', 'role': 'assistant', 'content': [], 'model': model, 'stop_reason': None, 'stop_sequence': None, 'usage': {'input_tokens': 10, 'output_tokens': 0}}},
                {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'thinking', 'thinking': '', 'signature': ''}},
            ]

            for char in Config.response_thinking_anthropic:
                events.append({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'thinking_delta', 'thinking': char}})

            events.append({'type': 'content_block_stop', 'index': 0})
            events.append({'type': 'content_block_start', 'index': 1, 'content_block': {'type': 'text', 'text': ''}})

            for char in Config.response_content_anthropic:
                events.append({'type': 'content_block_delta', 'index': 1, 'delta': {'type': 'text_delta', 'text': char}})

            events.append({'type': 'content_block_stop', 'index': 1})
            events.append({'type': 'message_delta', 'delta': {'stop_reason': 'end_turn', 'stop_sequence': None}, 'usage': {'output_tokens': 50}})
            events.append({'type': 'message_stop'})

            for event in events:
                data = {'type': event['type']}
                data.update({k: v for k, v in event.items() if k != 'type'})
                yield f'event: {event["type"]}\ndata: {json.dumps(data)}\n\n'
                if 'delta' in event:
                    time.sleep(0.01)

        return Response(generate(), mimetype='text/event-stream')

    return jsonify(response_data)


@server_app.route('/logs', methods=['GET'])
def api_get_logs():
    return jsonify({'count': len(get_logs()), 'logs': get_logs()})


@server_app.route('/logs/clear', methods=['POST'])
def api_clear_logs():
    clear_logs()
    return jsonify({'status': 'ok', 'message': '日志已清空'})


@server_app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'running', 'log_count': len(get_logs())})


def run_server(port=12312):
    server_app.run(host='127.0.0.1', port=port, debug=False, threaded=True, use_reloader=False)


# ============================================================
# GUI Application
# ============================================================

class MockServerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("API Mock Server - 本地接口模拟器")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)

        style = ttk.Style()
        style.theme_use('clam')

        # 使用PanedWindow实现左右分栏
        self.paned = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 左侧面板
        self.left_frame = ttk.Frame(self.paned)
        self.paned.add(self.left_frame, weight=2)

        # 右侧面板（配置面板）
        self.right_frame = ttk.Frame(self.paned)
        self.paned.add(self.right_frame, weight=1)

        self.create_left_panel()
        self.create_right_panel()

        self.start_server()
        self.refresh_logs()

    def create_left_panel(self):
        """左侧面板：控制+日志+详情"""
        # 控制面板
        control_frame = ttk.Frame(self.left_frame)
        control_frame.pack(fill='x')

        title_label = ttk.Label(control_frame, text="API Mock Server", font=('Microsoft YaHei', 14, 'bold'))
        title_label.pack(side='left')

        self.status_var = tk.StringVar(value="● 运行中")
        ttk.Label(control_frame, textvariable=self.status_var, foreground='green', font=('Microsoft YaHei', 10)).pack(side='left', padx=15)

        self.log_count_var = tk.StringVar(value="请求数: 0")
        ttk.Label(control_frame, textvariable=self.log_count_var, font=('Microsoft YaHei', 10)).pack(side='left', padx=5)

        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(side='right')
        ttk.Button(btn_frame, text="刷新日志", command=self.refresh_logs).pack(side='left', padx=3)
        ttk.Button(btn_frame, text="清空日志", command=self.on_clear).pack(side='left', padx=3)
        ttk.Button(btn_frame, text="导出JSON", command=self.export_json).pack(side='left', padx=3)
        ttk.Button(btn_frame, text="导出CSV", command=self.export_csv).pack(side='left', padx=3)

        # API地址和Key信息区
        self.create_info_panel()

        # 分隔线
        ttk.Separator(self.left_frame, orient='horizontal').pack(fill='x', pady=8)

        # 日志列表
        self.create_log_panel()

        # 详情面板
        self.create_detail_panel()

    def create_info_panel(self):
        """API地址和Key信息面板"""
        info_frame = ttk.LabelFrame(self.left_frame, text="接口信息", padding="5")
        info_frame.pack(fill='x', pady=(5, 0))

        # 每一行：标签 + 可复制Entry + 复制按钮
        entries = [
            ("OpenAI 接口:", f"http://localhost:{Config.port}/openai/v1/chat/completions"),
            ("Anthropic接口:", f"http://localhost:{Config.port}/anthropic/v1/messages"),
            ("日志 API:", f"http://localhost:{Config.port}/logs"),
            ("API Key:", Config.api_key),
        ]

        for label_text, value in entries:
            row = ttk.Frame(info_frame)
            row.pack(fill='x', pady=2)

            lbl = ttk.Label(row, text=label_text, width=14, font=('Microsoft YaHei', 9))
            lbl.pack(side='left')

            entry = ttk.Entry(row, font=('Consolas', 9))
            entry.insert(0, value)
            entry.config(state='readonly')
            entry.pack(side='left', fill='x', expand=True, padx=(0, 5))

            copy_btn = ttk.Button(row, text="复制", width=6, command=lambda e=entry: self.copy_entry(e))
            copy_btn.pack(side='left')

        # curl示例
        curl_frame = ttk.Frame(info_frame)
        curl_frame.pack(fill='x', pady=(5, 0))
        ttk.Label(curl_frame, text="调用示例:", font=('Microsoft YaHei', 9, 'bold')).pack(anchor='w')

        curl_example = (
            f'curl -X POST http://localhost:{Config.port}/openai/v1/chat/completions \\\n'
            f'  -H "Content-Type: application/json" \\\n'
            f'  -H "Authorization: Bearer {Config.api_key}" \\\n'
            f'  -d \'{{"model": "gpt-4", "messages": [{{"role": "user", "content": "hello"}}]}}\''
        )
        self.curl_text = scrolledtext.ScrolledText(curl_frame, wrap=tk.WORD, height=4, font=('Consolas', 8))
        self.curl_text.pack(fill='x', pady=(2, 0))
        self.curl_text.insert(tk.END, curl_example)
        self.curl_text.config(state='disabled')

    def copy_entry(self, entry):
        """复制Entry内容到剪贴板"""
        self.root.clipboard_clear()
        self.root.clipboard_append(entry.get())
        self.root.update()

    def create_log_panel(self):
        """日志列表面板"""
        log_frame = ttk.LabelFrame(self.left_frame, text="请求日志", padding="5")
        log_frame.pack(fill='both', expand=True)

        columns = ('时间', '类型', '模型', '客户端IP', 'User-Agent', '路径')
        self.tree = ttk.Treeview(log_frame, columns=columns, show='headings', height=10)

        col_widths = {'时间': 140, '类型': 70, '模型': 130, '客户端IP': 110, 'User-Agent': 250, '路径': 180}
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=col_widths.get(col, 100), minwidth=50)

        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        self.tree.bind('<<TreeviewSelect>>', self.on_log_select)

    def create_detail_panel(self):
        """详情面板"""
        detail_frame = ttk.LabelFrame(self.left_frame, text="请求详情", padding="5")
        detail_frame.pack(fill='both', expand=True, pady=(5, 0))

        self.notebook = ttk.Notebook(detail_frame)
        self.notebook.pack(fill='both', expand=True)

        headers_frame = ttk.Frame(self.notebook)
        self.headers_text = scrolledtext.ScrolledText(headers_frame, wrap=tk.WORD, height=6, font=('Consolas', 9))
        self.headers_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.notebook.add(headers_frame, text='请求 Headers')

        body_frame = ttk.Frame(self.notebook)
        self.body_text = scrolledtext.ScrolledText(body_frame, wrap=tk.WORD, height=6, font=('Consolas', 9))
        self.body_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.notebook.add(body_frame, text='请求 Body')

    def create_right_panel(self):
        """右侧面板：配置区"""
        config_frame = ttk.Frame(self.right_frame, padding="5")
        config_frame.pack(fill='both', expand=True)

        # ====== 服务器配置 ======
        server_frame = ttk.LabelFrame(config_frame, text="服务器配置", padding="8")
        server_frame.pack(fill='x', pady=(0, 10))

        ttk.Label(server_frame, text="监听端口:").pack(anchor='w')
        self.port_var = tk.StringVar(value=str(Config.port))
        port_entry = ttk.Entry(server_frame, textvariable=self.port_var, width=15, font=('Consolas', 10))
        port_entry.pack(anchor='w', pady=(2, 5))

        ttk.Label(server_frame, text="API Key:").pack(anchor='w')
        self.api_key_var = tk.StringVar(value=Config.api_key)
        key_entry = ttk.Entry(server_frame, textvariable=self.api_key_var, width=35, font=('Consolas', 9))
        key_entry.pack(anchor='w', pady=(2, 5))

        restart_btn = ttk.Button(server_frame, text="重启服务器（应用端口/API Key）", command=self.restart_server)
        restart_btn.pack(anchor='w', pady=(5, 0))

        # ====== 响应内容配置 ======
        response_frame = ttk.LabelFrame(config_frame, text="响应内容", padding="8")
        response_frame.pack(fill='x', pady=(0, 10))

        ttk.Label(response_frame, text="OpenAI Thinking:").pack(anchor='w')
        self.thinking_var = tk.Text(response_frame, height=3, width=40, font=('Microsoft YaHei', 9))
        self.thinking_var.pack(fill='x', pady=(2, 5))
        self.thinking_var.insert(tk.END, Config.response_thinking)

        ttk.Label(response_frame, text="OpenAI 结论:").pack(anchor='w')
        self.content_var = tk.Text(response_frame, height=3, width=40, font=('Microsoft YaHei', 9))
        self.content_var.pack(fill='x', pady=(2, 5))
        self.content_var.insert(tk.END, Config.response_content)

        ttk.Separator(response_frame, orient='horizontal').pack(fill='x', pady=5)

        ttk.Label(response_frame, text="Anthropic Thinking:").pack(anchor='w')
        self.thinking_a_var = tk.Text(response_frame, height=3, width=40, font=('Microsoft YaHei', 9))
        self.thinking_a_var.pack(fill='x', pady=(2, 5))
        self.thinking_a_var.insert(tk.END, Config.response_thinking_anthropic)

        ttk.Label(response_frame, text="Anthropic 结论:").pack(anchor='w')
        self.content_a_var = tk.Text(response_frame, height=3, width=40, font=('Microsoft YaHei', 9))
        self.content_a_var.pack(fill='x', pady=(2, 5))
        self.content_a_var.insert(tk.END, Config.response_content_anthropic)

        apply_btn = ttk.Button(response_frame, text="应用响应内容", command=self.apply_response_config)
        apply_btn.pack(anchor='w', pady=(5, 0))

        # ====== 延迟模拟 ======
        delay_frame = ttk.LabelFrame(config_frame, text="延迟模拟", padding="8")
        delay_frame.pack(fill='x', pady=(0, 10))

        ttk.Label(delay_frame, text="响应延迟 (秒):").pack(anchor='w')
        self.delay_var = tk.DoubleVar(value=Config.response_delay)
        delay_spinbox = ttk.Spinbox(delay_frame, from_=0, to=10, increment=0.1, textvariable=self.delay_var, width=12, font=('Consolas', 10))
        delay_spinbox.pack(anchor='w', pady=(2, 5))

        ttk.Label(delay_frame, text="模拟上游API的响应时间", font=('Microsoft YaHei', 8), foreground='#888').pack(anchor='w')

        # ====== 错误注入 ======
        error_frame = ttk.LabelFrame(config_frame, text="错误注入", padding="8")
        error_frame.pack(fill='x', pady=(0, 10))

        ttk.Label(error_frame, text="错误概率 (%):").pack(anchor='w')
        self.error_rate_var = tk.IntVar(value=Config.error_rate)
        error_spinbox = ttk.Spinbox(error_frame, from_=0, to=100, increment=5, textvariable=self.error_rate_var, width=10, font=('Consolas', 10))
        error_spinbox.pack(anchor='w', pady=(2, 5))

        ttk.Label(error_frame, text="错误状态码:").pack(anchor='w')
        self.error_code_var = tk.IntVar(value=Config.error_code)
        code_spinbox = ttk.Spinbox(error_frame, values=[500, 502, 503, 504], textvariable=self.error_code_var, width=10, font=('Consolas', 10))
        code_spinbox.pack(anchor='w', pady=(2, 5))

        ttk.Label(error_frame, text="错误信息:").pack(anchor='w')
        self.error_msg_var = tk.StringVar(value=Config.error_message)
        msg_entry = ttk.Entry(error_frame, textvariable=self.error_msg_var, width=35, font=('Consolas', 9))
        msg_entry.pack(anchor='w', pady=(2, 5))

        error_apply_btn = ttk.Button(error_frame, text="应用延迟和错误配置", command=self.apply_error_config)
        error_apply_btn.pack(anchor='w', pady=(5, 0))

    def start_server(self):
        def run():
            try:
                run_server(port=Config.port)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", f"服务器启动失败: {e}"))
                self.status_var.set("● 启动失败")

        threading.Thread(target=run, daemon=True).start()

    def restart_server(self):
        """重启服务器（端口变更时）"""
        try:
            new_port = int(self.port_var.get())
            if new_port < 1 or new_port > 65535:
                messagebox.showerror("错误", "端口号必须在 1-65535 之间")
                return
        except ValueError:
            messagebox.showerror("错误", "端口号必须是数字")
            return

        old_port = Config.port
        Config.port = new_port
        Config.api_key = self.api_key_var.get().strip()

        # 更新curl示例
        self.update_curl_example()

        if old_port != new_port:
            self.start_server()
            messagebox.showinfo("提示", f"服务器已在新端口 {new_port} 上启动")
        else:
            messagebox.showinfo("提示", f"API Key 已更新，端口保持 {new_port}")

    def update_curl_example(self):
        """更新curl示例"""
        curl_example = (
            f'curl -X POST http://localhost:{Config.port}/openai/v1/chat/completions \\\n'
            f'  -H "Content-Type: application/json" \\\n'
            f'  -H "Authorization: Bearer {Config.api_key}" \\\n'
            f'  -d \'{{"model": "gpt-4", "messages": [{{"role": "user", "content": "hello"}}]}}\''
        )
        self.curl_text.config(state='normal')
        self.curl_text.delete(1.0, tk.END)
        self.curl_text.insert(tk.END, curl_example)
        self.curl_text.config(state='disabled')

    def apply_response_config(self):
        """应用响应内容配置"""
        Config.response_thinking = self.thinking_var.get(1.0, tk.END).strip()
        Config.response_content = self.content_var.get(1.0, tk.END).strip()
        Config.response_thinking_anthropic = self.thinking_a_var.get(1.0, tk.END).strip()
        Config.response_content_anthropic = self.content_a_var.get(1.0, tk.END).strip()
        messagebox.showinfo("成功", "响应内容已更新")

    def apply_error_config(self):
        """应用延迟和错误配置"""
        Config.response_delay = self.delay_var.get()
        Config.error_rate = self.error_rate_var.get()
        Config.error_code = self.error_code_var.get()
        Config.error_message = self.error_msg_var.get().strip()
        messagebox.showinfo("成功", "延迟和错误配置已更新")

    def refresh_logs(self):
        try:
            logs = get_logs()
            self.log_count_var.set(f"请求数: {len(logs)}")

            for item in self.tree.get_children():
                self.tree.delete(item)

            for log in logs:
                self.tree.insert('', 'end', values=(
                    log.get('timestamp', ''),
                    log.get('api_type', '').upper(),
                    log.get('model', ''),
                    log.get('client_ip', ''),
                    log.get('user_agent', '')[:50],
                    log.get('path', '')
                ), tags=(log.get('id', ''),))
        except Exception as e:
            print(f"刷新日志出错: {e}")

        self.root.after(2000, self.refresh_logs)

    def on_clear(self):
        if messagebox.askyesno("确认", "确定要清空所有日志吗？"):
            clear_logs()
            self.refresh_logs()

    def on_log_select(self, event):
        selection = self.tree.selection()
        if not selection:
            return

        item = self.tree.item(selection[0])
        log_id = item['tags'][0] if item['tags'] else None

        if log_id:
            logs = get_logs()
            log = next((l for l in logs if l.get('id') == log_id), None)
            if log:
                headers = log.get('headers', {})
                self.headers_text.delete(1.0, tk.END)
                self.headers_text.insert(tk.END, json.dumps(headers, indent=2, ensure_ascii=False))

                body = log.get('body', {})
                self.body_text.delete(1.0, tk.END)
                self.body_text.insert(tk.END, json.dumps(body, indent=2, ensure_ascii=False))

    def export_json(self):
        """导出日志为JSON文件"""
        logs = get_logs()
        if not logs:
            messagebox.showinfo("提示", "没有可导出的日志")
            return

        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=f"mock_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        if filepath:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)
            messagebox.showinfo("成功", f"已导出 {len(logs)} 条日志到:\n{filepath}")

    def export_csv(self):
        """导出日志为CSV文件"""
        logs = get_logs()
        if not logs:
            messagebox.showinfo("提示", "没有可导出的日志")
            return

        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"mock_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        if filepath:
            with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['时间', '类型', '模型', '客户端IP', 'User-Agent', '路径', 'Content-Type', 'Auth Header'])
                for log in logs:
                    writer.writerow([
                        log.get('timestamp', ''),
                        log.get('api_type', ''),
                        log.get('model', ''),
                        log.get('client_ip', ''),
                        log.get('user_agent', ''),
                        log.get('path', ''),
                        log.get('content_type', ''),
                        log.get('auth_header', '')
                    ])
            messagebox.showinfo("成功", f"已导出 {len(logs)} 条日志到:\n{filepath}")


def main():
    root = tk.Tk()
    MockServerGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
