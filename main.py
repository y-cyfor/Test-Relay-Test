#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
API Mock Server v4.0 - 本地大模型接口模拟服务器
后端：FastAPI (通过 NiceGUI)
前端：NiceGUI Web 管理面板
"""

import os
import sys
import csv
import json
import time
import uuid
import math
import random
import asyncio
import threading
import webbrowser
from datetime import datetime
from collections import defaultdict
from fastapi import Request
from starlette.responses import Response, StreamingResponse

import urllib.request
import urllib.error
import urllib.parse
from urllib.parse import urljoin

FORWARD_TIMEOUT = 120

# ============================================================
# 全局配置
# ============================================================

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')

class Config:
    """全局配置"""
    port = 12312
    extra_ports = []
    api_key = "sk-mock-abc123def456ghi789"
    enable_auth = False
    max_logs = 1000
    enable_log_persistence = False
    enable_multi_turn = False

    forward_mode = False
    forward_openai_url = ""
    forward_openai_key = ""
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

    dark_mode = True

    @classmethod
    def to_dict(cls):
        return {
            'port': cls.port, 'extra_ports': cls.extra_ports,
            'api_key': cls.api_key, 'enable_auth': cls.enable_auth,
            'max_logs': cls.max_logs, 'enable_log_persistence': cls.enable_log_persistence,
            'enable_multi_turn': cls.enable_multi_turn,
            'forward_mode': cls.forward_mode,
            'forward_openai_url': cls.forward_openai_url, 'forward_openai_key': cls.forward_openai_key,
            'forward_anthropic_url': cls.forward_anthropic_url, 'forward_anthropic_key': cls.forward_anthropic_key,
            'response_thinking': cls.response_thinking, 'response_content': cls.response_content,
            'response_thinking_anthropic': cls.response_thinking_anthropic,
            'response_content_anthropic': cls.response_content_anthropic,
            'prompt_tokens': cls.prompt_tokens, 'completion_tokens': cls.completion_tokens,
            'response_delay': cls.response_delay, 'error_rate': cls.error_rate,
            'error_code': cls.error_code, 'error_message': cls.error_message,
            'dark_mode': cls.dark_mode,
        }

    @classmethod
    def from_dict(cls, data):
        for key, value in data.items():
            if hasattr(cls, key):
                setattr(cls, key, value)


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                Config.from_dict(json.load(f))
            return True
        except Exception:
            return False
    return False


def save_config():
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(Config.to_dict(), f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def ensure_log_dir():
    os.makedirs(LOGS_DIR, exist_ok=True)


def persist_log(entry):
    if not Config.enable_log_persistence:
        return
    ensure_log_dir()
    try:
        with open(os.path.join(LOGS_DIR, f'{datetime.now().strftime("%Y%m%d")}.jsonl'), 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:
        pass


# ============================================================
# 共享状态
# ============================================================

request_logs = []
logs_lock = threading.Lock()

stats_data = {
    'total': 0, 'openai': 0, 'anthropic': 0, 'errors': 0,
    'models': defaultdict(int), 'timestamps': [],
}
stats_lock = threading.Lock()


def update_stats(api_type, model, is_error=False):
    with stats_lock:
        stats_data['total'] += 1
        if is_error:
            stats_data['errors'] += 1
        elif api_type == 'openai':
            stats_data['openai'] += 1
        elif api_type == 'anthropic':
            stats_data['anthropic'] += 1
        stats_data['models'][model] += 1
        stats_data['timestamps'].append(time.time())
        if len(stats_data['timestamps']) > 1000:
            stats_data['timestamps'] = stats_data['timestamps'][-1000:]


def get_stats():
    with stats_lock:
        now = time.time()
        recent = [t for t in stats_data['timestamps'] if now - t < 60]
        intervals = [recent[i+1] - recent[i] for i in range(len(recent)-1)] if len(recent) > 1 else []
        return {
            'total': stats_data['total'], 'openai': stats_data['openai'],
            'anthropic': stats_data['anthropic'], 'errors': stats_data['errors'],
            'success_rate': round((stats_data['total'] - stats_data['errors']) / max(stats_data['total'], 1) * 100, 1),
            'rpm': len(recent),
            'avg_interval': round(sum(intervals) / len(intervals), 2) if intervals else 0,
            'models': dict(stats_data['models']),
        }


def add_log(entry):
    with logs_lock:
        request_logs.append(entry)
        if len(request_logs) > Config.max_logs:
            request_logs.pop(0)
        update_stats(entry.get('api_type', ''), entry.get('model', ''))
    persist_log(entry)


def get_logs():
    with logs_lock:
        return list(request_logs)


def clear_logs():
    global request_logs
    with logs_lock:
        request_logs = []


def maybe_inject_error():
    return Config.error_rate > 0 and random.randint(1, 100) <= Config.error_rate


def apply_delay():
    if Config.response_delay > 0:
        time.sleep(Config.response_delay)


# ============================================================
# 真实转发
# ============================================================

def forward_request(api_type, body_data: bytes, headers_in):
    if api_type == 'openai':
        base_url = Config.forward_openai_url.rstrip('/')
        path = '/v1/chat/completions'
        api_key = Config.forward_openai_key
    else:
        base_url = Config.forward_anthropic_url.rstrip('/')
        path = '/v1/messages'
        api_key = Config.forward_anthropic_key

    if not base_url:
        return 502, {}, json.dumps({'error': {'message': f'Forward failed: {api_type} upstream URL not configured', 'type': 'forward_error', 'code': 502}}).encode('utf-8')

    target_url = base_url + path if base_url.endswith('/') else base_url + path
    headers = {}
    for key, value in headers_in:
        if key.lower() in ('host', 'content-length'):
            continue
        headers[key] = value

    if api_type == 'openai' and api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    elif api_type == 'anthropic' and api_key:
        headers['x-api-key'] = api_key
        headers.setdefault('anthropic-version', '2023-06-01')

    headers['Content-Type'] = 'application/json'
    headers['Host'] = urllib.parse.urlparse(target_url).netloc

    req = urllib.request.Request(target_url, data=body_data, headers=headers, method='POST')

    try:
        with urllib.request.urlopen(req, timeout=FORWARD_TIMEOUT) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except urllib.error.URLError as e:
        return 502, {}, json.dumps({'error': {'message': f'Forward failed: {str(e.reason)}', 'type': 'forward_error', 'code': 502}}).encode('utf-8')
    except Exception as e:
        return 502, {}, json.dumps({'error': {'message': f'Forward timeout or unknown error: {str(e)}', 'type': 'forward_error', 'code': 502}}).encode('utf-8')


# ============================================================
# NiceGUI + API 路由
# ============================================================

from nicegui import ui, app


# --- API 路由 (直接使用 NiceGUI 的 app，底层是 FastAPI) ---

@app.post('/openai/v1/chat/completions')
async def openai_chat_completions(request: Request):
    from time import time as _time
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    if Config.enable_auth:
        auth_header = request.headers.get('Authorization', '')
        if auth_header != f'Bearer {Config.api_key}':
            model = body.get('model', 'unknown')
            add_log({
                'id': str(uuid.uuid4())[:8], 'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'method': 'POST', 'path': '/openai/v1/chat/completions',
                'model': model, 'client_ip': request.client.host,
                'user_agent': request.headers.get('user-agent', ''), 'content_type': request.headers.get('content-type', ''),
                'auth_header': auth_header[:20] + '...' if auth_header else '',
                'headers': dict(request.headers), 'body': body, 'api_type': 'openai', 'status': 401
            })
            update_stats('openai', model, is_error=True)
            return Response(status_code=401, content=json.dumps({'error': {'message': 'Invalid API Key', 'type': 'invalid_request_error', 'code': 401}}).encode(), media_type='application/json')

    model = body.get('model', 'unknown')
    add_log({
        'id': str(uuid.uuid4())[:8], 'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'method': 'POST', 'path': '/openai/v1/chat/completions',
        'model': model, 'client_ip': request.client.host,
        'user_agent': request.headers.get('user-agent', ''), 'content_type': request.headers.get('content-type', ''),
        'auth_header': request.headers.get('authorization', '')[:20] + '...' if request.headers.get('authorization') else '',
        'headers': dict(request.headers), 'body': body, 'api_type': 'openai', 'status': 200,
        'mode': 'forward' if Config.forward_mode else 'mock'
    })

    if Config.forward_mode:
        body_data = await request.body()
        status, _, resp_body = forward_request('openai', body_data, request.headers.raw)
        update_stats('openai', model, is_error=(status >= 500))
        return Response(content=resp_body, status_code=status, media_type='application/json')

    if maybe_inject_error():
        update_stats('openai', model, is_error=True)
        return Response(status_code=Config.error_code, content=json.dumps({'error': {'message': Config.error_message, 'type': 'server_error', 'code': Config.error_code}}).encode(), media_type='application/json')

    apply_delay()
    messages = body.get('messages', [])
    msg_count = len(messages) if Config.enable_multi_turn else 1
    usage = {'prompt_tokens': Config.prompt_tokens * msg_count, 'completion_tokens': Config.completion_tokens * msg_count, 'total_tokens': (Config.prompt_tokens + Config.completion_tokens) * msg_count}

    if Config.enable_multi_turn and msg_count > 1:
        content = ' '.join([Config.response_content] * msg_count)
        reasoning = ' '.join([Config.response_thinking] * msg_count)
    else:
        content = Config.response_content
        reasoning = Config.response_thinking

    resp = {
        'id': f'chatcmpl-{uuid.uuid4().hex[:10]}', 'object': 'chat.completion',
        'created': int(_time()), 'model': model,
        'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': content, 'reasoning_content': reasoning}, 'finish_reason': 'stop'}],
        'usage': usage
    }

    if body.get('stream', False):
        async def gen():
            for char in reasoning:
                yield f'data: {json.dumps({"id": f"chatcmpl-{uuid.uuid4().hex[:10]}", "object": "chat.completion.chunk", "created": int(_time()), "model": model, "choices": [{"index": 0, "delta": {"role": "assistant", "reasoning_content": char}, "finish_reason": None}]})}\n\n'
                await asyncio.sleep(0.01)
            for char in content:
                yield f'data: {json.dumps({"id": f"chatcmpl-{uuid.uuid4().hex[:10]}", "object": "chat.completion.chunk", "created": int(_time()), "model": model, "choices": [{"index": 0, "delta": {"content": char}, "finish_reason": None}]})}\n\n'
                await asyncio.sleep(0.01)
            yield f'data: {json.dumps({"id": f"chatcmpl-{uuid.uuid4().hex[:10]}", "object": "chat.completion.chunk", "created": int(_time()), "model": model, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})}\n\n'
            yield 'data: [DONE]\n\n'
        return StreamingResponse(gen(), media_type='text/event-stream')

    return Response(content=json.dumps(resp).encode(), media_type='application/json')


@app.post('/anthropic/v1/messages')
async def anthropic_messages(request: Request):
    from time import time as _time
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    if Config.enable_auth:
        x_api_key = request.headers.get('x-api-key', '')
        if x_api_key != Config.api_key:
            model = body.get('model', 'unknown')
            add_log({
                'id': str(uuid.uuid4())[:8], 'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'method': 'POST', 'path': '/anthropic/v1/messages',
                'model': model, 'client_ip': request.client.host,
                'user_agent': request.headers.get('user-agent', ''), 'content_type': request.headers.get('content-type', ''),
                'auth_header': x_api_key[:20] + '...' if x_api_key else '',
                'headers': dict(request.headers), 'body': body, 'api_type': 'anthropic', 'status': 401
            })
            update_stats('anthropic', model, is_error=True)
            return Response(status_code=401, content=json.dumps({'error': {'message': 'Invalid API Key', 'type': 'invalid_request_error', 'code': 401}}).encode(), media_type='application/json')

    model = body.get('model', 'unknown')
    add_log({
        'id': str(uuid.uuid4())[:8], 'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'method': 'POST', 'path': '/anthropic/v1/messages',
        'model': model, 'client_ip': request.client.host,
        'user_agent': request.headers.get('user-agent', ''), 'content_type': request.headers.get('content-type', ''),
        'auth_header': request.headers.get('x-api-key', '')[:20] + '...' if request.headers.get('x-api-key') else '',
        'anthropic_version': request.headers.get('anthropic-version', ''),
        'headers': dict(request.headers), 'body': body, 'api_type': 'anthropic', 'status': 200,
        'mode': 'forward' if Config.forward_mode else 'mock'
    })

    if Config.forward_mode:
        body_data = await request.body()
        status, _, resp_body = forward_request('anthropic', body_data, request.headers.raw)
        update_stats('anthropic', model, is_error=(status >= 500))
        return Response(content=resp_body, status_code=status, media_type='application/json')

    if maybe_inject_error():
        update_stats('anthropic', model, is_error=True)
        return Response(status_code=Config.error_code, content=json.dumps({'type': 'error', 'error': {'type': 'api_error', 'message': Config.error_message}}).encode(), media_type='application/json')

    apply_delay()
    messages = body.get('messages', [])
    msg_count = len(messages) if Config.enable_multi_turn else 1

    if Config.enable_multi_turn and msg_count > 1:
        content_blocks = []
        for i in range(msg_count):
            content_blocks.append({'type': 'thinking', 'thinking': Config.response_thinking_anthropic, 'signature': f'mock_signature_{i}'})
            content_blocks.append({'type': 'text', 'text': Config.response_content_anthropic})
    else:
        content_blocks = [
            {'type': 'thinking', 'thinking': Config.response_thinking_anthropic, 'signature': 'mock_signature_123'},
            {'type': 'text', 'text': Config.response_content_anthropic}
        ]

    resp = {
        'id': f'msg_{uuid.uuid4().hex[:12]}', 'type': 'message', 'role': 'assistant',
        'content': content_blocks, 'model': model, 'stop_reason': 'end_turn', 'stop_sequence': None,
        'usage': {'input_tokens': Config.prompt_tokens * msg_count, 'output_tokens': Config.completion_tokens * msg_count,
                  'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 0}
    }

    if body.get('stream', False):
        async def gen():
            events = [
                {'type': 'message_start', 'message': {'id': resp['id'], 'type': 'message', 'role': 'assistant', 'content': [], 'model': model, 'stop_reason': None, 'stop_sequence': None, 'usage': {'input_tokens': Config.prompt_tokens * msg_count, 'output_tokens': 0}}},
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
                    await asyncio.sleep(0.01)
        return StreamingResponse(gen(), media_type='text/event-stream')

    return Response(content=json.dumps(resp).encode(), media_type='application/json')


@app.get('/logs')
async def api_get_logs():
    return {'count': len(get_logs()), 'logs': get_logs()}


@app.post('/logs/clear')
async def api_clear_logs():
    clear_logs()
    return {'status': 'ok', 'message': '日志已清空'}


@app.get('/health')
async def health():
    return {'status': 'running', 'log_count': len(get_logs())}


@app.get('/stats')
async def api_stats():
    return get_stats()


# ============================================================
# NiceGUI Web 管理面板（模块级定义）
# ============================================================

# dark_mode 初始化在每个页面函数内部完成（避免触发 NiceGUI script_mode 冲突）

def _sidebar():
    """共享侧边栏"""
    with ui.left_drawer(fixed=True).classes('bg-gray-100 dark:bg-gray-800 w-56'):
        ui.label('导航').classes('text-sm font-bold px-4 py-3 text-gray-500 dark:text-gray-400')
        for label, path in [
            ('\U0001f4ca 仪表盘', '/'),
            ('\U0001f4dd 日志详情', '/logs-page'),
            ('\u2699\ufe0f 服务器配置', '/config'),
            ('\U0001f50c 端口管理', '/ports'),
            ('\u2139\ufe0f 接口信息', '/info'),
        ]:
            ui.button(label, on_click=lambda p=path: ui.navigate.to(p)).props('flat dense').classes('w-full justify-start text-left')

def _header(title_text, show_back=False):
    """共享顶部栏"""
    dark = ui.dark_mode()  # Inside page scope — avoids script_mode conflict
    with ui.header().classes('justify-between items-center bg-gradient-to-r from-blue-600 to-indigo-600 text-white px-4'):
        with ui.row().classes('items-center gap-3'):
            if show_back:
                ui.button(icon='arrow_back', on_click=lambda: ui.navigate.to('/')).props('flat dense')
            ui.icon('rocket', size='20px')
            ui.label(title_text).classes('text-lg font-bold')
        with ui.row().classes('items-center gap-2'):
            log_count_label = None
            if title_text == 'API Mock Server v4.0':
                ui.label('\u25cf 运行中').classes('text-green-300 text-sm')
                log_count_label = ui.label('请求数: 0').classes('text-sm')
            theme_label = ui.label('\U0001f319' if Config.dark_mode else '\u2600\ufe0f').classes('cursor-pointer')
            def toggle_theme():
                if dark.is_enabled:
                    dark.disable()
                    Config.dark_mode = False
                else:
                    dark.enable()
                    Config.dark_mode = True
                save_config()
                theme_label.set_text('\U0001f319' if Config.dark_mode else '\u2600\ufe0f')
                ui.notify(f'已切换到 {"深色" if Config.dark_mode else "浅色"} 主题', type='info')
            theme_label.on('click', toggle_theme)
        return log_count_label


# ---- 页面定义 ----

@ui.page('/')
def _dashboard():
    _sidebar()
    log_count_label = _header('API Mock Server v4.0')

    with ui.column().classes('w-full p-4 gap-4'):
        with ui.row().classes('w-full gap-3 flex-wrap'):
            cards = {}
            for icon, label, color, key in [
                ('bar_chart', '总请求', 'blue', 'total'),
                ('chat', 'OpenAI', 'green', 'openai'),
                ('smart_toy', 'Anthropic', 'purple', 'anthropic'),
                ('check_circle', '成功率', 'teal', 'success_rate'),
                ('speed', 'RPM', 'orange', 'rpm'),
                ('error_outline', '错误数', 'red', 'errors'),
            ]:
                with ui.card().classes('w-40 p-4 text-center'):
                    ui.icon(icon, size='28px').classes(f'text-{color}-500')
                    ui.label(label).classes('text-sm text-gray-500 dark:text-gray-400')
                    cards[key] = ui.label('0').classes(f'text-2xl font-bold text-{color}-600')

        with ui.card().classes('w-full p-4'):
            ui.label('模型调用次数').classes('text-lg font-bold mb-2')
            chart = ui.echart({
                'xAxis': {'type': 'category', 'data': []},
                'yAxis': {'type': 'value'},
                'series': [{'type': 'bar', 'data': [], 'itemStyle': {'color': '#4a90d9'}}],
                'grid': {'left': '3%', 'right': '4%', 'bottom': '3%', 'containLabel': True},
            }).classes('w-full h-48')

        with ui.card().classes('w-full p-4'):
            ui.label('最近请求').classes('text-lg font-bold mb-2')
            table = ui.table(columns=[
                {'name': 'timestamp', 'label': '时间', 'field': 'timestamp', 'sortable': True},
                {'name': 'api_type', 'label': '类型', 'field': 'api_type'},
                {'name': 'mode', 'label': '模式', 'field': 'mode'},
                {'name': 'model', 'label': '模型', 'field': 'model'},
                {'name': 'client_ip', 'label': 'IP', 'field': 'client_ip'},
                {'name': 'path', 'label': '路径', 'field': 'path'},
                {'name': 'status', 'label': '状态', 'field': 'status'},
            ], rows=[], row_key='id').classes('w-full')

        def refresh():
            logs = get_logs()
            stats = get_stats()
            for key in cards:
                val = stats.get(key, 0)
                cards[key].set_text(f"{val}%" if key == 'success_rate' else str(val))
            log_count_label.set_text(f"请求数: {len(logs)}")

            models = stats['models']
            if models:
                chart.options['xAxis']['data'] = list(models.keys())
                chart.options['series'][0]['data'] = list(models.values())
                chart.update()

            table.rows = [{
                'id': l['id'], 'timestamp': l['timestamp'], 'api_type': l['api_type'].upper(),
                'mode': l.get('mode', 'mock').upper(), 'model': l['model'],
                'client_ip': l['client_ip'], 'path': l['path'], 'status': str(l['status']),
            } for l in logs[-50:][::-1]]
            table.update()

        ui.timer(2.0, refresh)


@ui.page('/logs-page')
def _logs_page():
    _sidebar()
    _header('\U0001f4dd 日志详情', show_back=True)

    with ui.column().classes('w-full p-4 gap-4'):
        search_kw = [None]
        log_table = ui.table(columns=[
            {'name': 'timestamp', 'label': '时间', 'field': 'timestamp', 'sortable': True},
            {'name': 'api_type', 'label': '类型', 'field': 'api_type'},
            {'name': 'mode', 'label': '模式', 'field': 'mode'},
            {'name': 'model', 'label': '模型', 'field': 'model'},
            {'name': 'client_ip', 'label': 'IP', 'field': 'client_ip'},
            {'name': 'user_agent', 'label': 'UA', 'field': 'user_agent'},
            {'name': 'path', 'label': '路径', 'field': 'path'},
            {'name': 'status', 'label': '状态', 'field': 'status'},
        ], rows=[], row_key='id', pagination={'rowsPerPage': 20}).classes('w-full')

        with ui.card().classes('w-full p-4'):
            ui.label('请求详情 (点击表格行)').classes('text-lg font-bold mb-2')
            with ui.tabs().classes('w-full') as tabs:
                tab_h = ui.tab('Headers')
                tab_b = ui.tab('Body')
            with ui.tab_panels(tabs, value=tab_h).classes('w-full'):
                with ui.tab_panel(tab_h):
                    h_text = ui.textarea().props('readonly outlined').classes('w-full').style('min-height: 120px')
                with ui.tab_panel(tab_b):
                    b_text = ui.textarea().props('readonly outlined').classes('w-full').style('min-height: 120px')

        def refresh_logs_table():
            logs = get_logs()
            if search_kw[0]:
                logs = [l for l in logs if any(search_kw[0].lower() in str(v).lower() for v in l.values())]
                hint.set_text(f'找到 {len(logs)} 条')
            log_table.rows = [{
                'id': l['id'], 'timestamp': l['timestamp'], 'api_type': l['api_type'].upper(),
                'mode': l.get('mode', 'mock').upper(), 'model': l['model'],
                'client_ip': l['client_ip'],
                'user_agent': l.get('user_agent', '')[:50],
                'path': l['path'], 'status': str(l['status']),
            } for l in logs[-200:][::-1]]
            log_table.update()

        def do_search(kw):
            search_kw[0] = kw.strip() or None
            hint.set_text('')
            refresh_logs_table()

        def do_clear_search():
            search_kw[0] = None
            clear_logs()
            refresh_logs_table()
            ui.notify('日志已清空', type='info')

        def do_export_json():
            logs = get_logs()
            if not logs:
                ui.notify('没有日志', type='warning')
                return
            fp = os.path.join(os.getcwd(), f"mock_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            with open(fp, 'w', encoding='utf-8') as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)
            ui.notify(f'已导出到: {fp}', type='positive')

        def do_export_csv():
            logs = get_logs()
            if not logs:
                ui.notify('没有日志', type='warning')
                return
            fp = os.path.join(os.getcwd(), f"mock_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            with open(fp, 'w', newline='', encoding='utf-8-sig') as f:
                w = csv.writer(f)
                w.writerow(['时间', '类型', '模型', 'IP', 'UA', '路径', '状态'])
                for l in logs:
                    w.writerow([l['timestamp'], l['api_type'], l['model'], l['client_ip'], l.get('user_agent', ''), l['path'], l['status']])
            ui.notify(f'已导出到: {fp}', type='positive')

        def show_detail(e, h_ta, b_ta):
            row = e.args.get('row', {})
            log_id = row.get('id', '')
            log = next((l for l in get_logs() if l.get('id') == log_id), None)
            if log:
                h_ta.value = json.dumps(log.get('headers', {}), indent=2, ensure_ascii=False)
                b_ta.value = json.dumps(log.get('body', {}), indent=2, ensure_ascii=False)

        hint = ui.label('').classes('text-sm text-gray-500')
        search_input = ui.input(placeholder='搜索关键词...').classes('flex-grow')
        with ui.row().classes('w-full gap-2 items-center'):
            ui.button('搜索', on_click=lambda: do_search(search_input.value)).props('dense')
            ui.button('清除', on_click=do_clear_search).props('dense color=warning')
            ui.button('导出JSON', on_click=do_export_json).props('dense')
            ui.button('导出CSV', on_click=do_export_csv).props('dense')

        log_table.on('rowClick', lambda e: show_detail(e, h_text, b_text))

        ui.timer(2.0, refresh_logs_table)


@ui.page('/config')
def _config_page():
    _sidebar()
    _header('\u2699\ufe0f 服务器配置', show_back=True)

    with ui.column().classes('w-full p-4 gap-4 max-w-3xl'):
        with ui.card().classes('w-full p-4'):
            ui.label('服务器配置').classes('text-lg font-bold mb-3')
            port_inp = ui.number(label='监听端口', value=Config.port, format='%d').classes('w-40')
            key_inp = ui.input(label='API Key', value=Config.api_key).classes('w-full')
            auth_sw = ui.switch('启用 API Key 验证', value=Config.enable_auth)
            mt_sw = ui.switch('启用消息轮次响应', value=Config.enable_multi_turn)
            lp_sw = ui.switch('启用日志持久化', value=Config.enable_log_persistence)
            ml_inp = ui.number(label='最大日志数', value=Config.max_logs, format='%d').classes('w-40')

            def save_srv():
                Config.port = int(port_inp.value)
                Config.api_key = key_inp.value.strip()
                Config.enable_auth = auth_sw.value
                Config.enable_multi_turn = mt_sw.value
                Config.enable_log_persistence = lp_sw.value
                Config.max_logs = int(ml_inp.value)
                save_config()
                ui.notify('服务器配置已保存', type='positive')
            ui.button('保存', on_click=save_srv).props('color=blue')

        with ui.card().classes('w-full p-4'):
            ui.label('自定义响应').classes('text-lg font-bold mb-3')
            with ui.tabs().classes('w-full') as rt:
                to = ui.tab('OpenAI')
                ta = ui.tab('Anthropic')
            with ui.tab_panels(rt, value=to).classes('w-full'):
                with ui.tab_panel(to):
                    think_o = ui.textarea(label='Thinking', value=Config.response_thinking).classes('w-full')
                    cont_o = ui.textarea(label='结论', value=Config.response_content).classes('w-full')
                with ui.tab_panel(ta):
                    think_a = ui.textarea(label='Thinking', value=Config.response_thinking_anthropic).classes('w-full')
                    cont_a = ui.textarea(label='结论', value=Config.response_content_anthropic).classes('w-full')
            with ui.row().classes('gap-4'):
                pt_inp = ui.number(label='Prompt Tokens', value=Config.prompt_tokens, format='%d').classes('w-40')
                ct_inp = ui.number(label='Completion Tokens', value=Config.completion_tokens, format='%d').classes('w-40')

            def save_resp():
                Config.response_thinking = think_o.value.strip()
                Config.response_content = cont_o.value.strip()
                Config.response_thinking_anthropic = think_a.value.strip()
                Config.response_content_anthropic = cont_a.value.strip()
                Config.prompt_tokens = int(pt_inp.value)
                Config.completion_tokens = int(ct_inp.value)
                save_config()
                ui.notify('响应内容已更新', type='positive')
            ui.button('应用', on_click=save_resp).props('color=blue')

        with ui.card().classes('w-full p-4'):
            ui.label('延迟模拟 & 错误注入').classes('text-lg font-bold mb-3')
            with ui.row().classes('gap-4 flex-wrap'):
                delay_inp = ui.number(label='延迟 (秒)', value=Config.response_delay, format='%.1f').classes('w-40')
                er_inp = ui.number(label='错误概率 (%)', value=Config.error_rate, format='%d').classes('w-40')
                ec_inp = ui.number(label='状态码', value=Config.error_code, format='%d').classes('w-40')
            em_inp = ui.input(label='错误信息', value=Config.error_message).classes('w-full')

            def save_err():
                Config.response_delay = delay_inp.value
                Config.error_rate = int(er_inp.value)
                Config.error_code = int(ec_inp.value)
                Config.error_message = em_inp.value.strip()
                save_config()
                ui.notify('已更新', type='positive')
            ui.button('应用', on_click=save_err).props('color=blue')

        with ui.card().classes('w-full p-4'):
            ui.label('真实接口转发').classes('text-lg font-bold mb-3')
            fwd_sw = ui.switch('启用真实接口转发', value=Config.forward_mode)
            with ui.tabs().classes('w-full') as ft:
                tfo = ui.tab('OpenAI')
                tfa = ui.tab('Anthropic')
            with ui.tab_panels(ft, value=tfo).classes('w-full'):
                with ui.tab_panel(tfo):
                    fo_url = ui.input(label='Base URL', value=Config.forward_openai_url, placeholder='https://api.openai.com').classes('w-full')
                    fo_key = ui.input(label='API Key', value=Config.forward_openai_key, placeholder='sk-...').props('type=password').classes('w-full')
                with ui.tab_panel(tfa):
                    fa_url = ui.input(label='Base URL', value=Config.forward_anthropic_url, placeholder='https://api.anthropic.com').classes('w-full')
                    fa_key = ui.input(label='API Key', value=Config.forward_anthropic_key, placeholder='sk-ant-...').props('type=password').classes('w-full')

            def save_fwd():
                Config.forward_mode = fwd_sw.value
                Config.forward_openai_url = fo_url.value.strip()
                Config.forward_openai_key = fo_key.value.strip()
                Config.forward_anthropic_url = fa_url.value.strip()
                Config.forward_anthropic_key = fa_key.value.strip()
                save_config()
                ui.notify(f'已切换到 {"转发" if Config.forward_mode else "Mock"}', type='positive')
            ui.button('应用', on_click=save_fwd).props('color=blue')


@ui.page('/ports')
def _ports_page():
    _sidebar()
    _header('\U0001f50c 端口管理', show_back=True)

    with ui.column().classes('w-full p-4 gap-4 max-w-2xl'):
        with ui.card().classes('w-full p-4'):
            ui.label('额外端口').classes('text-lg font-bold mb-3')
            p_list = ui.list().classes('w-full')

            def refresh_p():
                p_list.clear()
                with p_list:
                    for pp in Config.extra_ports:
                        with ui.item().classes('flex justify-between items-center'):
                            with ui.item_section():
                                ui.label(f'端口 {pp}')
                            with ui.item_section():
                                ui.button('删除', on_click=lambda pp=pp: rm_p(pp)).props('dense color=red')

            def add_p(v):
                try:
                    v = int(v)
                    if 1 <= v <= 65535 and v not in Config.extra_ports and v != Config.port:
                        Config.extra_ports.append(v)
                        save_config()
                        refresh_p()
                        ui.notify(f'端口 {v} 已添加', type='positive')
                    else:
                        ui.notify('端口无效或已存在', type='negative')
                except:
                    ui.notify('请输入数字', type='negative')

            def rm_p(v):
                if v in Config.extra_ports:
                    Config.extra_ports.remove(v)
                    save_config()
                    refresh_p()

            def clr_p():
                Config.extra_ports.clear()
                save_config()
                refresh_p()
                ui.notify('已清除', type='positive')

            p_inp = ui.number(label='端口', format='%d').classes('w-40')
            with ui.row().classes('gap-2'):
                ui.button('添加', on_click=lambda: add_p(p_inp.value)).props('dense color=blue')
                ui.button('清除全部', on_click=clr_p).props('dense color=warning')

            refresh_p()


@ui.page('/info')
def _info_page():
    _sidebar()
    _header('\u2139\ufe0f 接口信息', show_back=True)

    with ui.column().classes('w-full p-4 gap-4 max-w-3xl'):
        with ui.card().classes('w-full p-4'):
            ui.label('接口地址').classes('text-lg font-bold mb-3')
            for lbl, val in [
                ('OpenAI', f'http://localhost:{Config.port}/openai/v1/chat/completions'),
                ('Anthropic', f'http://localhost:{Config.port}/anthropic/v1/messages'),
                ('日志 API', f'http://localhost:{Config.port}/logs'),
                ('API Key', Config.api_key),
            ]:
                with ui.row().classes('w-full items-center gap-2 mb-2'):
                    ui.label(lbl).classes('w-28 font-bold text-sm')
                    ui.input(value=val).props('readonly dense').classes('flex-grow')
                    ui.button('复制', on_click=lambda v=val: ui.notify(f'已复制: {v}', type='info')).props('dense')

            ui.label('调用示例').classes('text-lg font-bold mt-4 mb-2')
            ui.textarea(value=(
                f'curl -X POST http://localhost:{Config.port}/openai/v1/chat/completions \\\n'
                f'  -H "Content-Type: application/json" \\\n'
                f'  -H "Authorization: Bearer {Config.api_key}" \\\n'
                f'  -d \'{{"model": "gpt-4", "messages": [{{"role": "user", "content": "hello"}}]}}\''
            )).props('readonly outlined').classes('w-full').style('min-height: 80px; font-family: Consolas, monospace')


# ============================================================
# 启动
# ============================================================

def main():
    load_config()

    def open_browser():
        time.sleep(1.5)
        webbrowser.open(f'http://localhost:{Config.port}')

    threading.Thread(target=open_browser, daemon=True).start()

    ui.run(host='127.0.0.1', port=Config.port, title='API Mock Server v4.0',
           reload=False, show=False, dark=Config.dark_mode)


if __name__ == '__main__':
    main()
