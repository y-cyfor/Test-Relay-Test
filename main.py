#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
API Mock Server v3.0 - 本地大模型接口模拟服务器
GUI 使用 CustomTkinter 现代化框架
包含功能：API Key验证、日志搜索、日志限制、配置持久化、
Token可配置、多消息支持、深色主题、统计面板、
日志持久化、多端口并发、真实接口转发
"""

import os
import sys
import csv
import json
import time
import uuid
import math
import random
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import customtkinter as ctk
from datetime import datetime
from collections import defaultdict

from flask import Flask, request, jsonify, Response

# ============================================================
# 真实转发 - 使用 urllib 避免新增依赖
# ============================================================

import urllib.request
import urllib.error
import urllib.parse
from urllib.parse import urljoin

FORWARD_TIMEOUT = 120


def forward_request(api_type):
    """
    将请求原封不动转发到上游 API
    api_type: 'openai' 或 'anthropic'
    返回: (status_code, headers_dict, body_bytes_or_str)
    """
    if api_type == 'openai':
        base_url = Config.forward_openai_url.rstrip('/')
        path = '/v1/chat/completions'
        api_key = Config.forward_openai_key
    else:
        base_url = Config.forward_anthropic_url.rstrip('/')
        path = '/v1/messages'
        api_key = Config.forward_anthropic_key

    if not base_url:
        return 502, {}, json.dumps({
            'error': {
                'message': f'Forward failed: {api_type} upstream URL not configured',
                'type': 'forward_error',
                'code': 502
            }
        }).encode('utf-8')

    target_url = base_url + path if base_url.endswith('/') else base_url + path

    # 构建转发请求
    body_data = request.get_data()
    headers = {}
    for key, value in request.headers:
        # 跳过 Flask 自动添加的 host
        if key.lower() in ('host', 'content-length'):
            continue
        headers[key] = value

    # 确保上游认证
    if api_type == 'openai' and api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    elif api_type == 'anthropic' and api_key:
        headers['x-api-key'] = api_key
        if 'anthropic-version' not in headers:
            headers['anthropic-version'] = '2023-06-01'

    headers['Content-Type'] = 'application/json'
    headers['Host'] = urllib.parse.urlparse(target_url).netloc

    req = urllib.request.Request(target_url, data=body_data, headers=headers, method='POST')

    try:
        with urllib.request.urlopen(req, timeout=FORWARD_TIMEOUT) as resp:
            resp_body = resp.read()
            resp_headers = dict(resp.headers)
            return resp.status, resp_headers, resp_body
    except urllib.error.HTTPError as e:
        err_body = e.read()
        return e.code, dict(e.headers), err_body
    except urllib.error.URLError as e:
        return 502, {}, json.dumps({
            'error': {
                'message': f'Forward failed: {str(e.reason)}',
                'type': 'forward_error',
                'code': 502
            }
        }).encode('utf-8')
    except Exception as e:
        return 502, {}, json.dumps({
            'error': {
                'message': f'Forward timeout or unknown error: {str(e)}',
                'type': 'forward_error',
                'code': 502
            }
        }).encode('utf-8')


# ============================================================
# 全局配置
# ============================================================

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')

class Config:
    """全局配置，GUI和Server共享"""
    port = 12312
    extra_ports = []  # [(port_number, running_flag), ...]
    api_key = "sk-mock-abc123def456ghi789"
    enable_auth = False
    max_logs = 1000
    enable_log_persistence = False
    enable_multi_turn = False

    # 真实转发配置
    forward_mode = False
    # OpenAI 转发
    forward_openai_url = ""
    forward_openai_key = ""
    # Anthropic 转发
    forward_anthropic_url = ""
    forward_anthropic_key = ""

    response_thinking = "这是Mock服务器模拟的thinking过程。首先分析用户的问题，然后逐步推理得出结论。整个过程展示了thinking功能的转发是否正常。"
    response_content = "这是一个Mock服务器返回的固定结论内容。你的API中转平台转发功能正常！"
    response_thinking_anthropic = "这是Mock服务器模拟的thinking过程。Anthropic的thinking块展示了模型的推理过程，用于验证thinking功能是否正常转发。"
    response_content_anthropic = "这是一个Mock服务器返回的固定结论内容。你的API中转平台转发功能正常！Anthropic接口测试通过。"

    prompt_tokens = 10
    completion_tokens = 50

    response_delay = 0.0
    error_rate = 0
    error_code = 500
    error_message = "Internal Server Error"

    dark_mode = False

    @classmethod
    def to_dict(cls):
        return {
            'port': cls.port,
            'extra_ports': cls.extra_ports,
            'api_key': cls.api_key,
            'enable_auth': cls.enable_auth,
            'max_logs': cls.max_logs,
            'enable_log_persistence': cls.enable_log_persistence,
            'enable_multi_turn': cls.enable_multi_turn,
            'forward_mode': cls.forward_mode,
            'forward_openai_url': cls.forward_openai_url,
            'forward_openai_key': cls.forward_openai_key,
            'forward_anthropic_url': cls.forward_anthropic_url,
            'forward_anthropic_key': cls.forward_anthropic_key,
            'response_thinking': cls.response_thinking,
            'response_content': cls.response_content,
            'response_thinking_anthropic': cls.response_thinking_anthropic,
            'response_content_anthropic': cls.response_content_anthropic,
            'prompt_tokens': cls.prompt_tokens,
            'completion_tokens': cls.completion_tokens,
            'response_delay': cls.response_delay,
            'error_rate': cls.error_rate,
            'error_code': cls.error_code,
            'error_message': cls.error_message,
            'dark_mode': cls.dark_mode,
        }

    @classmethod
    def from_dict(cls, data):
        for key, value in data.items():
            if hasattr(cls, key):
                setattr(cls, key, value)


def load_config():
    """从config.json加载配置"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            Config.from_dict(data)
            return True
        except Exception:
            return False
    return False


def save_config():
    """保存配置到config.json"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(Config.to_dict(), f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def ensure_log_dir():
    """确保日志目录存在"""
    os.makedirs(LOGS_DIR, exist_ok=True)


def persist_log(log_entry):
    """持久化单条日志到JSONL文件"""
    if not Config.enable_log_persistence:
        return
    ensure_log_dir()
    today = datetime.now().strftime('%Y%m%d')
    filepath = os.path.join(LOGS_DIR, f'{today}.jsonl')
    try:
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    except Exception:
        pass


# ============================================================
# Flask Server (内嵌)
# ============================================================

server_app = Flask(__name__)

request_logs = []
logs_lock = threading.Lock()

# 统计数据
stats_data = {
    'total': 0,
    'openai': 0,
    'anthropic': 0,
    'errors': 0,
    'models': defaultdict(int),
    'timestamps': [],
}
stats_lock = threading.Lock()


def update_stats(api_type, model, is_error=False):
    with stats_lock:
        stats_data['total'] += 1
        if is_error:
            stats_data['errors'] += 1
        else:
            if api_type == 'openai':
                stats_data['openai'] += 1
            elif api_type == 'anthropic':
                stats_data['anthropic'] += 1
        stats_data['models'][model] += 1
        stats_data['timestamps'].append(time.time())
        # 保留最近1000条时间戳
        if len(stats_data['timestamps']) > 1000:
            stats_data['timestamps'] = stats_data['timestamps'][-1000:]


def get_stats():
    with stats_lock:
        now = time.time()
        recent = [t for t in stats_data['timestamps'] if now - t < 60]
        # 计算平均请求间隔
        if len(recent) > 1:
            intervals = [recent[i+1] - recent[i] for i in range(len(recent)-1)]
            avg_interval = sum(intervals) / len(intervals)
        else:
            avg_interval = 0
        return {
            'total': stats_data['total'],
            'openai': stats_data['openai'],
            'anthropic': stats_data['anthropic'],
            'errors': stats_data['errors'],
            'success_rate': round((stats_data['total'] - stats_data['errors']) / max(stats_data['total'], 1) * 100, 1),
            'rpm': len(recent),
            'avg_interval': round(avg_interval, 2),
            'models': dict(stats_data['models']),
        }


def add_log(entry):
    with logs_lock:
        request_logs.append(entry)
        if len(request_logs) > Config.max_logs:
            removed = request_logs.pop(0)
        # 更新统计
        update_stats(entry.get('api_type', ''), entry.get('model', ''), False)
    # 持久化
    persist_log(entry)


def get_logs():
    with logs_lock:
        return list(request_logs)


def clear_logs():
    global request_logs
    with logs_lock:
        request_logs = []


def maybe_inject_error():
    if Config.error_rate > 0 and random.randint(1, 100) <= Config.error_rate:
        return True
    return False


def apply_delay():
    if Config.response_delay > 0:
        time.sleep(Config.response_delay)


def check_auth(api_type):
    """检查API Key认证"""
    if not Config.enable_auth:
        return True
    if api_type == 'openai':
        auth_header = request.headers.get('Authorization', '')
        expected = f'Bearer {Config.api_key}'
        return auth_header == expected
    elif api_type == 'anthropic':
        return request.headers.get('x-api-key', '') == Config.api_key
    return False


def auth_error_response():
    return jsonify({
        'error': {
            'message': 'Invalid API Key',
            'type': 'invalid_request_error',
            'code': 401
        }
    }), 401


@server_app.route('/openai/v1/chat/completions', methods=['POST'])
def openai_chat_completions():
    from time import time as _time

    # 鉴权
    if not check_auth('openai'):
        entry = {
            'id': str(uuid.uuid4())[:8],
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'method': request.method, 'path': request.path,
            'model': '', 'client_ip': request.remote_addr,
            'user_agent': request.headers.get('User-Agent', ''),
            'content_type': request.headers.get('Content-Type', ''),
            'auth_header': request.headers.get('Authorization', '')[:20] + '...',
            'headers': dict(request.headers), 'body': {},
            'api_type': 'openai', 'status': 401
        }
        add_log(entry)
        update_stats('openai', '', is_error=True)
        return auth_error_response()

    body = request.get_json(silent=True) or {}
    model = body.get('model', 'unknown')

    log_entry = {
        'id': str(uuid.uuid4())[:8],
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'method': request.method, 'path': request.path,
        'model': model, 'client_ip': request.remote_addr,
        'user_agent': request.headers.get('User-Agent', ''),
        'content_type': request.headers.get('Content-Type', ''),
        'auth_header': request.headers.get('Authorization', '')[:20] + '...' if request.headers.get('Authorization') else '',
        'headers': dict(request.headers), 'body': body,
        'api_type': 'openai', 'status': 200,
        'mode': 'forward' if Config.forward_mode else 'mock'
    }
    add_log(log_entry)

    # 转发模式：真实请求上游
    if Config.forward_mode:
        status, resp_headers, resp_body = forward_request('openai')
        if status >= 500:
            update_stats('openai', model, is_error=True)
        else:
            update_stats('openai', model)
        return Response(resp_body, status=status, content_type='application/json')

    if maybe_inject_error():
        update_stats('openai', model, is_error=True)
        return jsonify({
            'error': {'message': Config.error_message, 'type': 'server_error', 'code': Config.error_code}
        }), Config.error_code

    apply_delay()

    messages = body.get('messages', [])
    msg_count = len(messages) if Config.enable_multi_turn else 1

    usage = {
        'prompt_tokens': Config.prompt_tokens * msg_count,
        'completion_tokens': Config.completion_tokens * msg_count,
        'total_tokens': (Config.prompt_tokens + Config.completion_tokens) * msg_count
    }

    # 构建内容
    if Config.enable_multi_turn and msg_count > 1:
        content = ' '.join([Config.response_content] * msg_count)
        reasoning = ' '.join([Config.response_thinking] * msg_count)
    else:
        content = Config.response_content
        reasoning = Config.response_thinking

    response_data = {
        'id': f'chatcmpl-{uuid.uuid4().hex[:10]}',
        'object': 'chat.completion',
        'created': int(_time()),
        'model': model,
        'choices': [{
            'index': 0,
            'message': {
                'role': 'assistant',
                'content': content,
                'reasoning_content': reasoning
            },
            'finish_reason': 'stop'
        }],
        'usage': usage
    }

    if body.get('stream', False):
        def generate():
            for char in reasoning:
                chunk = {
                    'id': f'chatcmpl-{uuid.uuid4().hex[:10]}',
                    'object': 'chat.completion.chunk',
                    'created': int(_time()), 'model': model,
                    'choices': [{'index': 0, 'delta': {'role': 'assistant', 'reasoning_content': char}, 'finish_reason': None}]
                }
                yield f'data: {json.dumps(chunk)}\n\n'
                time.sleep(0.01)

            for char in content:
                chunk = {
                    'id': f'chatcmpl-{uuid.uuid4().hex[:10]}',
                    'object': 'chat.completion.chunk',
                    'created': int(_time()), 'model': model,
                    'choices': [{'index': 0, 'delta': {'content': char}, 'finish_reason': None}]
                }
                yield f'data: {json.dumps(chunk)}\n\n'
                time.sleep(0.01)

            chunk = {
                'id': f'chatcmpl-{uuid.uuid4().hex[:10]}',
                'object': 'chat.completion.chunk',
                'created': int(_time()), 'model': model,
                'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]
            }
            yield f'data: {json.dumps(chunk)}\n\n'
            yield 'data: [DONE]\n\n'

        return Response(generate(), mimetype='text/event-stream')

    return jsonify(response_data)


@server_app.route('/anthropic/v1/messages', methods=['POST'])
def anthropic_messages():
    from time import time as _time

    # 鉴权
    if not check_auth('anthropic'):
        entry = {
            'id': str(uuid.uuid4())[:8],
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'method': request.method, 'path': request.path,
            'model': '', 'client_ip': request.remote_addr,
            'user_agent': request.headers.get('User-Agent', ''),
            'content_type': request.headers.get('Content-Type', ''),
            'auth_header': request.headers.get('x-api-key', '')[:20] + '...',
            'headers': dict(request.headers), 'body': {},
            'api_type': 'anthropic', 'status': 401
        }
        add_log(entry)
        update_stats('anthropic', '', is_error=True)
        return auth_error_response()

    body = request.get_json(silent=True) or {}
    model = body.get('model', 'unknown')

    log_entry = {
        'id': str(uuid.uuid4())[:8],
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'method': request.method, 'path': request.path,
        'model': model, 'client_ip': request.remote_addr,
        'user_agent': request.headers.get('User-Agent', ''),
        'content_type': request.headers.get('Content-Type', ''),
        'auth_header': request.headers.get('x-api-key', '')[:20] + '...' if request.headers.get('x-api-key') else '',
        'anthropic_version': request.headers.get('anthropic-version', ''),
        'headers': dict(request.headers), 'body': body,
        'api_type': 'anthropic', 'status': 200,
        'mode': 'forward' if Config.forward_mode else 'mock'
    }
    add_log(log_entry)

    # 转发模式：真实请求上游
    if Config.forward_mode:
        status, resp_headers, resp_body = forward_request('anthropic')
        if status >= 500:
            update_stats('anthropic', model, is_error=True)
        else:
            update_stats('anthropic', model)
        return Response(resp_body, status=status, content_type='application/json')

    if maybe_inject_error():
        update_stats('anthropic', model, is_error=True)
        return jsonify({
            'type': 'error',
            'error': {'type': 'api_error', 'message': Config.error_message}
        }), Config.error_code

    apply_delay()

    messages = body.get('messages', [])
    msg_count = len(messages) if Config.enable_multi_turn else 1

    content_blocks = []
    if Config.enable_multi_turn and msg_count > 1:
        for i in range(msg_count):
            content_blocks.append({
                'type': 'thinking',
                'thinking': Config.response_thinking_anthropic,
                'signature': f'mock_signature_{i}'
            })
            content_blocks.append({
                'type': 'text',
                'text': Config.response_content_anthropic
            })
    else:
        content_blocks = [
            {'type': 'thinking', 'thinking': Config.response_thinking_anthropic, 'signature': 'mock_signature_123'},
            {'type': 'text', 'text': Config.response_content_anthropic}
        ]

    response_data = {
        'id': f'msg_{uuid.uuid4().hex[:12]}',
        'type': 'message',
        'role': 'assistant',
        'content': content_blocks,
        'model': model,
        'stop_reason': 'end_turn',
        'stop_sequence': None,
        'usage': {
            'input_tokens': Config.prompt_tokens * msg_count,
            'output_tokens': Config.completion_tokens * msg_count,
            'cache_creation_input_tokens': 0,
            'cache_read_input_tokens': 0
        }
    }

    if body.get('stream', False):
        def generate():
            events = [
                {'type': 'message_start', 'message': {
                    'id': response_data['id'], 'type': 'message', 'role': 'assistant',
                    'content': [], 'model': model, 'stop_reason': None, 'stop_sequence': None,
                    'usage': {'input_tokens': Config.prompt_tokens * msg_count, 'output_tokens': 0}
                }},
                {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'thinking', 'thinking': '', 'signature': ''}},
            ]

            for char in Config.response_thinking_anthropic:
                events.append({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'thinking_delta', 'thinking': char}})

            events.append({'type': 'content_block_stop', 'index': 0})
            events.append({'type': 'content_block_start', 'index': 1, 'content_block': {'type': 'text', 'text': ''}})

            for char in Config.response_content_anthropic:
                events.append({'type': 'content_block_delta', 'index': 1, 'delta': {'type': 'text_delta', 'text': char}})

            events.append({'type': 'content_block_stop', 'index': 1})
            events.append({'type': 'message_delta', 'delta': {'stop_reason': 'end_turn', 'stop_sequence': None}, 'usage': {'output_tokens': Config.completion_tokens * msg_count}})
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


@server_app.route('/stats', methods=['GET'])
def api_stats():
    return jsonify(get_stats())


def run_server(port=12312):
    server_app.run(host='127.0.0.1', port=port, debug=False, threaded=True, use_reloader=False)


# ============================================================
# GUI Application
# ============================================================

class MockServerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("API Mock Server v3.0 - 本地接口模拟器")
        self.root.geometry("1350x900")
        self.root.minsize(1100, 750)

        # CustomTkinter 主题
        ctk.set_appearance_mode("Dark" if Config.dark_mode else "Light")
        ctk.set_default_color_theme("blue")

        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.tray_icon = None
        self._closing = False

        self._build_ui()

        self.start_server()
        self.refresh_logs()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _apply_ttk_theme_colors(self):
        """同步 Treeview 颜色以匹配 CTk 主题"""
        dark = Config.dark_mode
        self.style.configure('Treeview',
            background='#2b2b2b' if dark else '#f5f5f5',
            foreground='#ffffff' if dark else '#000000',
            fieldbackground='#2b2b2b' if dark else '#f5f5f5',
            borderwidth=0)
        self.style.configure('Treeview.Heading',
            background='#3a3a3a' if dark else '#e0e0e0',
            foreground='#ffffff' if dark else '#000000',
            relief='flat')
        self.style.map('Treeview.Heading',
            background=[('active', '#4a4a4a' if dark else '#d0d0d0')])
        self.style.configure('TScrollbar',
            background='#3a3a3a' if dark else '#c0c0c0')

    def _build_ui(self):
        self._apply_ttk_theme_colors()

        self.paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.left_frame = ctk.CTkFrame(self.paned, fg_color='transparent')
        self.paned.add(self.left_frame, weight=2)

        self.right_frame = ctk.CTkFrame(self.paned, fg_color='transparent')
        self.paned.add(self.right_frame, weight=1)

        self.create_left_panel()
        self.create_right_panel()

    def create_left_panel(self):
        # 顶部控制栏
        control_frame = ctk.CTkFrame(self.left_frame, fg_color='transparent')
        control_frame.pack(fill='x')

        title_label = ctk.CTkLabel(control_frame, text="API Mock Server v3.0",
            font=('Microsoft YaHei', 16, 'bold'))
        title_label.pack(side='left')

        self.status_var = tk.StringVar(value="● 运行中")
        ctk.CTkLabel(control_frame, textvariable=self.status_var,
            text_color='#4CAF50', font=('Microsoft YaHei', 10)).pack(side='left', padx=15)

        self.log_count_var = tk.StringVar(value="请求数: 0")
        ctk.CTkLabel(control_frame, textvariable=self.log_count_var,
            font=('Microsoft YaHei', 10)).pack(side='left', padx=5)

        # 主题切换按钮
        theme_text = "浅色" if Config.dark_mode else "深色"
        self.theme_button = ctk.CTkButton(control_frame, text=f"{theme_text}主题",
            command=self.toggle_theme, width=80)
        self.theme_button.pack(side='right', padx=3)

        btn_frame = ctk.CTkFrame(control_frame, fg_color='transparent')
        btn_frame.pack(side='right')
        ctk.CTkButton(btn_frame, text="刷新日志", command=self.refresh_logs, width=80).pack(side='left', padx=2)
        ctk.CTkButton(btn_frame, text="清空日志", command=self.on_clear, width=80).pack(side='left', padx=2)
        ctk.CTkButton(btn_frame, text="导出JSON", command=self.export_json, width=80).pack(side='left', padx=2)
        ctk.CTkButton(btn_frame, text="导出CSV", command=self.export_csv, width=80).pack(side='left', padx=2)

        # API信息
        self.create_info_panel()

        # 分隔线
        ctk.CTkFrame(self.left_frame, height=2, fg_color=('gray20', 'gray80')).pack(fill='x', pady=10)

        # 日志列表 + 搜索
        self.create_log_panel()

        # 详情面板 / 统计
        self.create_bottom_tabs()

    def create_info_panel(self):
        info_frame = ctk.CTkFrame(self.left_frame, corner_radius=10)
        info_frame.pack(fill='x', pady=(5, 0))

        ctk.CTkLabel(info_frame, text="接口信息", font=('Microsoft YaHei', 11, 'bold')).pack(
            anchor='w', padx=12, pady=(8, 4))

        entries = [
            ("OpenAI 接口:", f"http://localhost:{Config.port}/openai/v1/chat/completions"),
            ("Anthropic接口:", f"http://localhost:{Config.port}/anthropic/v1/messages"),
            ("日志 API:", f"http://localhost:{Config.port}/logs"),
            ("API Key:", Config.api_key),
        ]

        for label_text, value in entries:
            row = ctk.CTkFrame(info_frame, fg_color='transparent')
            row.pack(fill='x', padx=10, pady=2)

            ctk.CTkLabel(row, text=label_text, width=110, anchor='w',
                font=('Microsoft YaHei', 9)).pack(side='left')
            entry = ctk.CTkEntry(row, width=400, font=('Consolas', 9))
            entry.insert(0, value)
            entry.configure(state='readonly')
            entry.pack(side='left', fill='x', expand=True, padx=(0, 5))
            ctk.CTkButton(row, text="复制", width=50, command=lambda e=entry: self.copy_entry(e)).pack(side='left')

        ctk.CTkLabel(info_frame, text="调用示例:", font=('Microsoft YaHei', 9, 'bold')).pack(
            anchor='w', padx=12, pady=(8, 2))

        self.curl_text = ctk.CTkTextbox(info_frame, height=80, font=('Consolas', 8))
        self.curl_text.pack(fill='x', padx=10, pady=(0, 8))
        self._update_curl_text()
        self.curl_text.configure(state='disabled')

    def _update_curl_text(self):
        curl = (
            f'curl -X POST http://localhost:{Config.port}/openai/v1/chat/completions \\\n'
            f'  -H "Content-Type: application/json" \\\n'
            f'  -H "Authorization: Bearer {Config.api_key}" \\\n'
            f'  -d \'{{"model": "gpt-4", "messages": [{{"role": "user", "content": "hello"}}]}}\''
        )
        self.curl_text.configure(state='normal')
        self.curl_text.delete(1.0, tk.END)
        self.curl_text.insert(tk.END, curl)
        self.curl_text.configure(state='disabled')

    def copy_entry(self, entry):
        self.root.clipboard_clear()
        self.root.clipboard_append(entry.get())
        self.root.update()

    def create_log_panel(self):
        log_frame = ctk.CTkFrame(self.left_frame, corner_radius=10)
        log_frame.pack(fill='both', expand=True)

        # 搜索栏
        search_frame = ctk.CTkFrame(log_frame, fg_color='transparent')
        search_frame.pack(fill='x', pady=(8, 5), padx=8)

        ctk.CTkLabel(search_frame, text="搜索:", font=('Microsoft YaHei', 9)).pack(side='left')
        self.search_var = tk.StringVar()
        search_entry = ctk.CTkEntry(search_frame, textvariable=self.search_var,
            width=200, placeholder_text="输入关键词...", font=('Consolas', 9))
        search_entry.pack(side='left', padx=5)
        search_entry.bind('<Return>', lambda e: self.search_logs())
        ctk.CTkButton(search_frame, text="搜索", command=self.search_logs, width=50).pack(side='left', padx=2)
        ctk.CTkButton(search_frame, text="清除", command=self.clear_search, width=50).pack(side='left', padx=2)

        self.search_hint = ctk.CTkLabel(search_frame, text="", text_color='gray', font=('Microsoft YaHei', 8))
        self.search_hint.pack(side='right')

        # 日志Treeview (保留 ttk)
        tree_container = ctk.CTkFrame(log_frame, fg_color='transparent')
        tree_container.pack(fill='both', expand=True, padx=8, pady=(0, 8))

        columns = ('时间', '类型', '模式', '模型', '客户端IP', 'User-Agent', '路径', '状态')
        self.tree = ttk.Treeview(tree_container, columns=columns, show='headings', height=8)

        col_widths = {'时间': 125, '类型': 60, '模式': 50, '模型': 110, '客户端IP': 95, 'User-Agent': 180, '路径': 150, '状态': 50}
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=col_widths.get(col, 100), minwidth=50)

        scrollbar = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        self.tree.bind('<<TreeviewSelect>>', self.on_log_select)

    def create_bottom_tabs(self):
        detail_frame = ctk.CTkFrame(self.left_frame, corner_radius=10)
        detail_frame.pack(fill='both', expand=True, pady=(5, 0))

        # 使用 CTkTabview
        self.tabview = ctk.CTkTabview(detail_frame)
        self.tabview.pack(fill='both', expand=True, padx=5, pady=5)

        # Headers 页
        headers_frame = self.tabview.add('请求 Headers')
        self.headers_text = ctk.CTkTextbox(headers_frame, font=('Consolas', 9))
        self.headers_text.pack(fill='both', expand=True, padx=8, pady=8)

        # Body 页
        body_frame = self.tabview.add('请求 Body')
        self.body_text = ctk.CTkTextbox(body_frame, font=('Consolas', 9))
        self.body_text.pack(fill='both', expand=True, padx=8, pady=8)

        # 统计页
        stats_frame = self.tabview.add('统计面板')
        self._create_stats_ui(stats_frame)

    def _create_stats_ui(self, parent):
        self.stats_frame = parent
        # 统计信息标签
        stats_labels = ['总请求数', 'OpenAI请求', 'Anthropic请求', '错误数', '成功率', 'RPM(近1分钟)', '平均间隔(秒)']
        self.stat_vars = {}
        for i, label in enumerate(stats_labels):
            row = ctk.CTkFrame(self.stats_frame, fg_color='transparent')
            row.pack(fill='x', pady=2, padx=8)
            ctk.CTkLabel(row, text=f"{label}:", width=130, anchor='w',
                font=('Microsoft YaHei', 9)).pack(side='left')
            var = tk.StringVar(value="0")
            self.stat_vars[label] = var
            ctk.CTkLabel(row, textvariable=var, font=('Consolas', 10, 'bold')).pack(side='left')

        # 模型调用次数 Canvas
        ctk.CTkLabel(self.stats_frame, text="模型调用次数:", font=('Microsoft YaHei', 9, 'bold')).pack(
            anchor='w', padx=8, pady=(10, 5))
        self.stats_canvas = tk.Canvas(self.stats_frame, height=150,
            bg='#2b2b2b' if Config.dark_mode else '#f5f5f5')
        self.stats_canvas.pack(fill='x', padx=8, pady=5)

    def update_stats_ui(self):
        stats = get_stats()
        self.stat_vars['总请求数'].set(str(stats['total']))
        self.stat_vars['OpenAI请求'].set(str(stats['openai']))
        self.stat_vars['Anthropic请求'].set(str(stats['anthropic']))
        self.stat_vars['错误数'].set(str(stats['errors']))
        self.stat_vars['成功率'].set(f"{stats['success_rate']}%")
        self.stat_vars['RPM(近1分钟)'].set(str(stats['rpm']))
        self.stat_vars['平均间隔(秒)'].set(str(stats['avg_interval']))
        self._draw_bar_chart(stats['models'])

    def _draw_bar_chart(self, models):
        if not models:
            return
        self.stats_canvas.delete('all')
        canvas_width = self.stats_canvas.winfo_width() or 500
        canvas_height = 150

        max_val = max(models.values()) if models else 1
        bar_width = min(60, (canvas_width - 40) // max(len(models), 1))
        gap = 10
        total_width = len(models) * (bar_width + gap)
        start_x = (canvas_width - total_width) // 2

        dark = Config.dark_mode
        bg_color = '#2b2b2b' if dark else '#f5f5f5'
        text_color = '#ffffff' if dark else '#000000'

        self.stats_canvas.create_rectangle(0, 0, canvas_width, canvas_height, fill=bg_color, outline='')

        for i, (model, count) in enumerate(models.items()):
            x = start_x + i * (bar_width + gap)
            bar_height = int((count / max(max_val, 1)) * (canvas_height - 40))
            y = canvas_height - 20 - bar_height

            self.stats_canvas.create_rectangle(x, y, x + bar_width, canvas_height - 20, fill='#4a90d9', outline='')
            self.stats_canvas.create_text(x + bar_width // 2, canvas_height - 8,
                text=model[:8], fill=text_color, font=('Microsoft YaHei', 7))
            self.stats_canvas.create_text(x + bar_width // 2, y - 5,
                text=str(count), fill=text_color, font=('Consolas', 8, 'bold'))

    def search_logs(self):
        keyword = self.search_var.get().strip().lower()
        if not keyword:
            self.refresh_logs()
            return

        logs = get_logs()
        filtered = [l for l in logs if any(
            keyword in str(v).lower() for v in l.values()
        )]

        for item in self.tree.get_children():
            self.tree.delete(item)

        for log in filtered:
            self.tree.insert('', 'end', values=(
                log.get('timestamp', ''),
                log.get('api_type', '').upper(),
                log.get('mode', 'mock').upper(),
                log.get('model', ''),
                log.get('client_ip', ''),
                log.get('user_agent', '')[:35],
                log.get('path', ''),
                log.get('status', '200')
            ), tags=(log.get('id', ''),))

        self.search_hint.configure(text=f"找到 {len(filtered)} 条")

    def clear_search(self):
        self.search_var.set('')
        self.search_hint.configure(text='')
        self.refresh_logs()

    def create_right_panel(self):
        config_frame = ctk.CTkFrame(self.right_frame, fg_color='transparent')
        config_frame.pack(fill='both', expand=True)

        # ====== 服务器配置 ======
        server_frame = ctk.CTkFrame(config_frame, corner_radius=10)
        server_frame.pack(fill='x', pady=(0, 10))

        ctk.CTkLabel(server_frame, text="服务器配置", font=('Microsoft YaHei', 11, 'bold')).pack(
            anchor='w', padx=12, pady=(8, 4))

        ctk.CTkLabel(server_frame, text="监听端口:", font=('Microsoft YaHei', 9)).pack(anchor='w', padx=12)
        self.port_var = tk.StringVar(value=str(Config.port))
        ctk.CTkEntry(server_frame, textvariable=self.port_var, width=120,
            font=('Consolas', 10)).pack(anchor='w', padx=12, pady=(2, 5))

        ctk.CTkLabel(server_frame, text="API Key:", font=('Microsoft YaHei', 9)).pack(anchor='w', padx=12)
        self.api_key_var = tk.StringVar(value=Config.api_key)
        ctk.CTkEntry(server_frame, textvariable=self.api_key_var, width=300,
            font=('Consolas', 9)).pack(anchor='w', padx=12, pady=(2, 5))

        self.auth_var = tk.BooleanVar(value=Config.enable_auth)
        ctk.CTkSwitch(server_frame, text="启用API Key验证", variable=self.auth_var,
            font=('Microsoft YaHei', 9)).pack(anchor='w', padx=12, pady=(2, 2))

        self.multi_turn_var = tk.BooleanVar(value=Config.enable_multi_turn)
        ctk.CTkSwitch(server_frame, text="启用消息轮次响应", variable=self.multi_turn_var,
            font=('Microsoft YaHei', 9)).pack(anchor='w', padx=12, pady=(2, 2))

        self.log_persist_var = tk.BooleanVar(value=Config.enable_log_persistence)
        ctk.CTkSwitch(server_frame, text="启用日志持久化", variable=self.log_persist_var,
            font=('Microsoft YaHei', 9)).pack(anchor='w', padx=12, pady=(2, 5))

        ctk.CTkLabel(server_frame, text="最大日志数:", font=('Microsoft YaHei', 9)).pack(anchor='w', padx=12)
        self.max_logs_var = tk.IntVar(value=Config.max_logs)
        ttk.Spinbox(server_frame, from_=100, to=10000, increment=100,
            textvariable=self.max_logs_var, width=12, font=('Consolas', 10)).pack(anchor='w', padx=12, pady=(2, 8))

        ctk.CTkButton(server_frame, text="重启服务器", command=self.restart_server,
            width=120, fg_color='#2196F3').pack(anchor='w', padx=12, pady=(0, 8))

        # ====== 多端口配置 ======
        port_frame = ctk.CTkFrame(config_frame, corner_radius=10)
        port_frame.pack(fill='x', pady=(0, 10))

        ctk.CTkLabel(port_frame, text="额外端口", font=('Microsoft YaHei', 11, 'bold')).pack(
            anchor='w', padx=12, pady=(8, 4))

        extra_row = ctk.CTkFrame(port_frame, fg_color='transparent')
        extra_row.pack(fill='x', padx=12, pady=(0, 5))
        self.extra_port_var = tk.StringVar()
        ctk.CTkEntry(extra_row, textvariable=self.extra_port_var, width=80,
            placeholder_text="端口号", font=('Consolas', 10)).pack(side='left')
        ctk.CTkButton(extra_row, text="添加", command=self.add_extra_port, width=50).pack(side='left', padx=5)
        ctk.CTkButton(extra_row, text="清除全部", command=self.clear_extra_ports, width=60).pack(side='left')

        self.extra_ports_listbox = tk.Listbox(port_frame, height=3, font=('Consolas', 9),
            bg='#2b2b2b' if Config.dark_mode else '#ffffff',
            fg='#ffffff' if Config.dark_mode else '#000000')
        self.extra_ports_listbox.pack(fill='x', padx=12, pady=(0, 8))
        for p in Config.extra_ports:
            self.extra_ports_listbox.insert(tk.END, str(p))

        # ====== 响应模式 Tabview ======
        mode_tabview = ctk.CTkTabview(config_frame)
        mode_tabview.pack(fill='both', expand=True)

        # --- Tab 1: 自定义响应 ---
        mock_tab = mode_tabview.add("自定义响应")

        ctk.CTkLabel(mock_tab, text="OpenAI Thinking:", font=('Microsoft YaHei', 9)).pack(anchor='w', padx=8, pady=(4, 0))
        self.thinking_var = tk.Text(mock_tab, height=2, width=40, font=('Microsoft YaHei', 9),
            bg='#2b2b2b' if Config.dark_mode else '#ffffff',
            fg='#ffffff' if Config.dark_mode else '#000000',
            insertbackground='#ffffff' if Config.dark_mode else '#000000')
        self.thinking_var.pack(fill='x', padx=8, pady=(2, 5))
        self.thinking_var.insert(tk.END, Config.response_thinking)

        ctk.CTkLabel(mock_tab, text="OpenAI 结论:", font=('Microsoft YaHei', 9)).pack(anchor='w', padx=8)
        self.content_var = tk.Text(mock_tab, height=2, width=40, font=('Microsoft YaHei', 9),
            bg='#2b2b2b' if Config.dark_mode else '#ffffff',
            fg='#ffffff' if Config.dark_mode else '#000000',
            insertbackground='#ffffff' if Config.dark_mode else '#000000')
        self.content_var.pack(fill='x', padx=8, pady=(2, 5))
        self.content_var.insert(tk.END, Config.response_content)

        # 分隔线
        ctk.CTkFrame(mock_tab, height=2, fg_color=('gray20', 'gray80')).pack(fill='x', pady=5)

        ctk.CTkLabel(mock_tab, text="Anthropic Thinking:", font=('Microsoft YaHei', 9)).pack(anchor='w', padx=8)
        self.thinking_a_var = tk.Text(mock_tab, height=2, width=40, font=('Microsoft YaHei', 9),
            bg='#2b2b2b' if Config.dark_mode else '#ffffff',
            fg='#ffffff' if Config.dark_mode else '#000000',
            insertbackground='#ffffff' if Config.dark_mode else '#000000')
        self.thinking_a_var.pack(fill='x', padx=8, pady=(2, 5))
        self.thinking_a_var.insert(tk.END, Config.response_thinking_anthropic)

        ctk.CTkLabel(mock_tab, text="Anthropic 结论:", font=('Microsoft YaHei', 9)).pack(anchor='w', padx=8)
        self.content_a_var = tk.Text(mock_tab, height=2, width=40, font=('Microsoft YaHei', 9),
            bg='#2b2b2b' if Config.dark_mode else '#ffffff',
            fg='#ffffff' if Config.dark_mode else '#000000',
            insertbackground='#ffffff' if Config.dark_mode else '#000000')
        self.content_a_var.pack(fill='x', padx=8, pady=(2, 5))
        self.content_a_var.insert(tk.END, Config.response_content_anthropic)

        ctk.CTkFrame(mock_tab, height=2, fg_color=('gray20', 'gray80')).pack(fill='x', pady=5)

        # Token配置
        token_row = ctk.CTkFrame(mock_tab, fg_color='transparent')
        token_row.pack(fill='x', pady=(0, 5), padx=8)
        ctk.CTkLabel(token_row, text="Prompt Tokens:", font=('Microsoft YaHei', 9)).pack(side='left')
        self.prompt_tokens_var = tk.IntVar(value=Config.prompt_tokens)
        ttk.Spinbox(token_row, from_=1, to=10000, textvariable=self.prompt_tokens_var,
            width=8, font=('Consolas', 9)).pack(side='left', padx=5)
        ctk.CTkLabel(token_row, text="Completion Tokens:", font=('Microsoft YaHei', 9)).pack(side='left', padx=(10, 0))
        self.completion_tokens_var = tk.IntVar(value=Config.completion_tokens)
        ttk.Spinbox(token_row, from_=1, to=10000, textvariable=self.completion_tokens_var,
            width=8, font=('Consolas', 9)).pack(side='left', padx=5)

        ctk.CTkButton(mock_tab, text="应用响应内容", command=self.apply_response_config,
            width=120).pack(anchor='w', padx=8, pady=(5, 5))

        # 延迟模拟
        delay_frame = ctk.CTkFrame(mock_tab, corner_radius=10)
        delay_frame.pack(fill='x', pady=(5, 5), padx=8)
        ctk.CTkLabel(delay_frame, text="延迟模拟", font=('Microsoft YaHei', 10, 'bold')).pack(
            anchor='w', padx=10, pady=(6, 2))
        ctk.CTkLabel(delay_frame, text="响应延迟 (秒):", font=('Microsoft YaHei', 9)).pack(anchor='w', padx=10)
        self.delay_var = tk.DoubleVar(value=Config.response_delay)
        ttk.Spinbox(delay_frame, from_=0, to=10, increment=0.1, textvariable=self.delay_var,
            width=12, font=('Consolas', 10)).pack(anchor='w', padx=10, pady=(2, 6))

        # 错误注入
        error_frame = ctk.CTkFrame(mock_tab, corner_radius=10)
        error_frame.pack(fill='x', pady=(0, 5), padx=8)
        ctk.CTkLabel(error_frame, text="错误注入", font=('Microsoft YaHei', 10, 'bold')).pack(
            anchor='w', padx=10, pady=(6, 2))
        ctk.CTkLabel(error_frame, text="错误概率 (%):", font=('Microsoft YaHei', 9)).pack(anchor='w', padx=10)
        self.error_rate_var = tk.IntVar(value=Config.error_rate)
        ttk.Spinbox(error_frame, from_=0, to=100, increment=5, textvariable=self.error_rate_var,
            width=10, font=('Consolas', 10)).pack(anchor='w', padx=10, pady=(2, 3))
        ctk.CTkLabel(error_frame, text="错误状态码:", font=('Microsoft YaHei', 9)).pack(anchor='w', padx=10)
        self.error_code_var = tk.IntVar(value=Config.error_code)
        ttk.Spinbox(error_frame, values=[500, 502, 503, 504], textvariable=self.error_code_var,
            width=10, font=('Consolas', 10)).pack(anchor='w', padx=10, pady=(2, 3))
        ctk.CTkLabel(error_frame, text="错误信息:", font=('Microsoft YaHei', 9)).pack(anchor='w', padx=10)
        self.error_msg_var = tk.StringVar(value=Config.error_message)
        ctk.CTkEntry(error_frame, textvariable=self.error_msg_var, width=300,
            font=('Consolas', 9)).pack(anchor='w', padx=10, pady=(2, 6))
        ctk.CTkButton(error_frame, text="应用延迟和错误配置", command=self.apply_error_config,
            width=150).pack(anchor='w', padx=10, pady=(0, 8))

        # --- Tab 2: 真实转发 ---
        forward_tab = mode_tabview.add("真实转发")

        self.forward_var = tk.BooleanVar(value=Config.forward_mode)
        ctk.CTkSwitch(forward_tab, text="启用真实接口转发", variable=self.forward_var,
            font=('Microsoft YaHei', 10)).pack(anchor='w', padx=12, pady=(8, 10))

        # OpenAI 转发
        openai_fwd = ctk.CTkFrame(forward_tab, corner_radius=10)
        openai_fwd.pack(fill='x', padx=8, pady=(0, 10))
        ctk.CTkLabel(openai_fwd, text="OpenAI 兼容接口", font=('Microsoft YaHei', 10, 'bold')).pack(
            anchor='w', padx=10, pady=(6, 2))
        ctk.CTkLabel(openai_fwd, text="Base URL:", font=('Microsoft YaHei', 9)).pack(anchor='w', padx=10)
        self.forward_openai_url_var = tk.StringVar(value=Config.forward_openai_url)
        ctk.CTkEntry(openai_fwd, textvariable=self.forward_openai_url_var, width=300,
            placeholder_text="https://api.openai.com", font=('Consolas', 9)).pack(anchor='w', padx=10, pady=(2, 3))
        ctk.CTkLabel(openai_fwd, text="API Key:", font=('Microsoft YaHei', 9)).pack(anchor='w', padx=10)
        self.forward_openai_key_var = tk.StringVar(value=Config.forward_openai_key)
        ctk.CTkEntry(openai_fwd, textvariable=self.forward_openai_key_var, width=300,
            placeholder_text="sk-...", font=('Consolas', 9), show='*').pack(anchor='w', padx=10, pady=(2, 6))

        # Anthropic 转发
        anthropic_fwd = ctk.CTkFrame(forward_tab, corner_radius=10)
        anthropic_fwd.pack(fill='x', padx=8, pady=(0, 10))
        ctk.CTkLabel(anthropic_fwd, text="Anthropic 兼容接口", font=('Microsoft YaHei', 10, 'bold')).pack(
            anchor='w', padx=10, pady=(6, 2))
        ctk.CTkLabel(anthropic_fwd, text="Base URL:", font=('Microsoft YaHei', 9)).pack(anchor='w', padx=10)
        self.forward_anthropic_url_var = tk.StringVar(value=Config.forward_anthropic_url)
        ctk.CTkEntry(anthropic_fwd, textvariable=self.forward_anthropic_url_var, width=300,
            placeholder_text="https://api.anthropic.com", font=('Consolas', 9)).pack(anchor='w', padx=10, pady=(2, 3))
        ctk.CTkLabel(anthropic_fwd, text="API Key:", font=('Microsoft YaHei', 9)).pack(anchor='w', padx=10)
        self.forward_anthropic_key_var = tk.StringVar(value=Config.forward_anthropic_key)
        ctk.CTkEntry(anthropic_fwd, textvariable=self.forward_anthropic_key_var, width=300,
            placeholder_text="sk-ant-...", font=('Consolas', 9), show='*').pack(anchor='w', padx=10, pady=(2, 6))

        ctk.CTkLabel(forward_tab, text="OpenAI接口请求转发到OpenAI上游，Anthropic接口请求转发到Anthropic上游",
            font=('Microsoft YaHei', 8), text_color='gray', wraplength=300).pack(anchor='w', padx=12, pady=(0, 10))

        ctk.CTkButton(forward_tab, text="应用转发配置", command=self.apply_forward_config,
            width=120, fg_color='#2196F3').pack(anchor='w', padx=12, pady=(0, 8))

    def toggle_theme(self):
        Config.dark_mode = not Config.dark_mode
        mode = "Dark" if Config.dark_mode else "Light"
        ctk.set_appearance_mode(mode)
        self._apply_ttk_theme_colors()
        theme_text = "浅色" if Config.dark_mode else "深色"
        self.theme_button.configure(text=f"{theme_text}主题")
        # 更新 Listbox 和 Text 颜色
        bg = '#2b2b2b' if Config.dark_mode else '#ffffff'
        fg = '#ffffff' if Config.dark_mode else '#000000'
        self.extra_ports_listbox.configure(bg=bg, fg=fg)
        self.stats_canvas.configure(bg=bg)
        for txt in [self.thinking_var, self.content_var, self.thinking_a_var, self.content_a_var]:
            txt.configure(bg=bg, fg=fg, insertbackground=fg)

    def add_extra_port(self):
        try:
            port = int(self.extra_port_var.get())
            if port < 1 or port > 65535:
                messagebox.showerror("错误", "端口号必须在 1-65535 之间")
                return
            if port in Config.extra_ports or port == Config.port:
                messagebox.showerror("错误", "端口已存在")
                return
            Config.extra_ports.append(port)
            self.extra_ports_listbox.insert(tk.END, str(port))
            self.extra_port_var.set('')
            threading.Thread(target=lambda: run_server(port), daemon=True).start()
            messagebox.showinfo("成功", f"已在端口 {port} 启动服务")
        except ValueError:
            messagebox.showerror("错误", "端口号必须是数字")

    def clear_extra_ports(self):
        Config.extra_ports.clear()
        self.extra_ports_listbox.delete(0, tk.END)

    def start_server(self):
        def run():
            try:
                run_server(port=Config.port)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", f"服务器启动失败: {e}"))
                self.status_var.set("● 启动失败")

        threading.Thread(target=run, daemon=True).start()
        for port in Config.extra_ports:
            threading.Thread(target=lambda p=port: run_server(p), daemon=True).start()

    def restart_server(self):
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
        Config.enable_auth = self.auth_var.get()
        Config.enable_multi_turn = self.multi_turn_var.get()
        Config.enable_log_persistence = self.log_persist_var.get()
        Config.max_logs = self.max_logs_var.get()
        Config.forward_mode = self.forward_var.get()
        Config.forward_openai_url = self.forward_openai_url_var.get().strip()
        Config.forward_openai_key = self.forward_openai_key_var.get().strip()
        Config.forward_anthropic_url = self.forward_anthropic_url_var.get().strip()
        Config.forward_anthropic_key = self.forward_anthropic_key_var.get().strip()
        save_config()
        self._update_curl_text()

        if old_port != new_port:
            self.start_server()
            messagebox.showinfo("提示", f"服务器已在新端口 {new_port} 上启动")
        else:
            messagebox.showinfo("提示", "配置已更新")

    def apply_response_config(self):
        Config.response_thinking = self.thinking_var.get(1.0, tk.END).strip()
        Config.response_content = self.content_var.get(1.0, tk.END).strip()
        Config.response_thinking_anthropic = self.thinking_a_var.get(1.0, tk.END).strip()
        Config.response_content_anthropic = self.content_a_var.get(1.0, tk.END).strip()
        Config.prompt_tokens = self.prompt_tokens_var.get()
        Config.completion_tokens = self.completion_tokens_var.get()
        save_config()
        messagebox.showinfo("成功", "响应内容已更新")

    def apply_error_config(self):
        Config.response_delay = self.delay_var.get()
        Config.error_rate = self.error_rate_var.get()
        Config.error_code = self.error_code_var.get()
        Config.error_message = self.error_msg_var.get().strip()
        save_config()
        messagebox.showinfo("成功", "延迟和错误配置已更新")

    def apply_forward_config(self):
        Config.forward_mode = self.forward_var.get()
        Config.forward_openai_url = self.forward_openai_url_var.get().strip()
        Config.forward_openai_key = self.forward_openai_key_var.get().strip()
        Config.forward_anthropic_url = self.forward_anthropic_url_var.get().strip()
        Config.forward_anthropic_key = self.forward_anthropic_key_var.get().strip()
        save_config()
        mode_text = "转发模式" if Config.forward_mode else "Mock模式"
        messagebox.showinfo("成功", f"已切换到 {mode_text}")

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
                    log.get('mode', 'mock').upper(),
                    log.get('model', ''),
                    log.get('client_ip', ''),
                    log.get('user_agent', '')[:35],
                    log.get('path', ''),
                    log.get('status', '200')
                ), tags=(log.get('id', ''),))

            self.update_stats_ui()
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
                self.headers_text.configure(state='normal')
                self.headers_text.delete(1.0, tk.END)
                self.headers_text.insert(tk.END, json.dumps(headers, indent=2, ensure_ascii=False))

                body = log.get('body', {})
                self.body_text.configure(state='normal')
                self.body_text.delete(1.0, tk.END)
                self.body_text.insert(tk.END, json.dumps(body, indent=2, ensure_ascii=False))

    def export_json(self):
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
                writer.writerow(['时间', '类型', '模型', '客户端IP', 'User-Agent', '路径', '状态', 'Content-Type', 'Auth Header'])
                for log in logs:
                    writer.writerow([
                        log.get('timestamp', ''), log.get('api_type', ''), log.get('model', ''),
                        log.get('client_ip', ''), log.get('user_agent', ''), log.get('path', ''),
                        log.get('status', '200'), log.get('content_type', ''), log.get('auth_header', '')
                    ])
            messagebox.showinfo("成功", f"已导出 {len(logs)} 条日志到:\n{filepath}")

    def on_close(self):
        if messagebox.askokcancel("退出", "确定要退出 API Mock Server 吗？"):
            self.root.quit()
            self.root.destroy()


def main():
    # 加载持久化配置
    load_config()

    root = ctk.CTk()
    MockServerGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
