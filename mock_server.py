#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
API Mock Server - 本地大模型接口模拟服务器
用于测试API中转平台的请求转发和伪装功能
"""

import json
import time
import uuid
import threading
from datetime import datetime
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

# 全局请求日志存储
request_logs = []
logs_lock = threading.Lock()


def add_log(entry):
    """添加请求日志"""
    with logs_lock:
        request_logs.append(entry)


def get_logs():
    """获取所有请求日志"""
    with logs_lock:
        return list(request_logs)


def clear_logs():
    """清空日志"""
    global request_logs
    with logs_lock:
        request_logs = []


@app.route('/openai/v1/chat/completions', methods=['POST'])
def openai_chat_completions():
    """OpenAI 兼容接口"""
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

    # 构建 OpenAI 格式响应
    response_data = {
        'id': f'chatcmpl-{uuid.uuid4().hex[:10]}',
        'object': 'chat.completion',
        'created': int(time.time()),
        'model': model,
        'choices': [{
            'index': 0,
            'message': {
                'role': 'assistant',
                'content': '这是一个Mock服务器返回的固定结论内容。你的API中转平台转发功能正常！',
                'reasoning_content': '这是Mock服务器模拟的thinking过程。首先分析用户的问题，然后逐步推理得出结论。整个过程展示了thinking功能的转发是否正常。'
            },
            'finish_reason': 'stop'
        }],
        'usage': {
            'prompt_tokens': 10,
            'completion_tokens': 50,
            'total_tokens': 60
        }
    }

    # 流式响应支持
    if body.get('stream', False):
        def generate():
            # 先发送 reasoning_content
            reasoning = '这是Mock服务器模拟的thinking过程。首先分析用户的问题，然后逐步推理得出结论。整个过程展示了thinking功能的转发是否正常。'
            for char in reasoning:
                chunk = {
                    'id': f'chatcmpl-{uuid.uuid4().hex[:10]}',
                    'object': 'chat.completion.chunk',
                    'created': int(time.time()),
                    'model': model,
                    'choices': [{
                        'index': 0,
                        'delta': {'role': 'assistant', 'reasoning_content': char},
                        'finish_reason': None
                    }]
                }
                yield f'data: {json.dumps(chunk)}\n\n'
                time.sleep(0.01)

            # 再发送 content
            content = '这是一个Mock服务器返回的固定结论内容。你的API中转平台转发功能正常！'
            for char in content:
                chunk = {
                    'id': f'chatcmpl-{uuid.uuid4().hex[:10]}',
                    'object': 'chat.completion.chunk',
                    'created': int(time.time()),
                    'model': model,
                    'choices': [{
                        'index': 0,
                        'delta': {'content': char},
                        'finish_reason': None
                    }]
                }
                yield f'data: {json.dumps(chunk)}\n\n'
                time.sleep(0.01)

            # 发送结束标记
            chunk = {
                'id': f'chatcmpl-{uuid.uuid4().hex[:10]}',
                'object': 'chat.completion.chunk',
                'created': int(time.time()),
                'model': model,
                'choices': [{
                    'index': 0,
                    'delta': {},
                    'finish_reason': 'stop'
                }]
            }
            yield f'data: {json.dumps(chunk)}\n\n'
            yield 'data: [DONE]\n\n'

        return Response(generate(), mimetype='text/event-stream')

    return jsonify(response_data)


@app.route('/anthropic/v1/messages', methods=['POST'])
def anthropic_messages():
    """Anthropic 兼容接口"""
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

    # 构建 Anthropic 格式响应
    response_data = {
        'id': f'msg_{uuid.uuid4().hex[:12]}',
        'type': 'message',
        'role': 'assistant',
        'content': [
            {
                'type': 'thinking',
                'thinking': '这是Mock服务器模拟的thinking过程。Anthropic的thinking块展示了模型的推理过程，用于验证thinking功能是否正常转发。',
                'signature': 'mock_signature_123'
            },
            {
                'type': 'text',
                'text': '这是一个Mock服务器返回的固定结论内容。你的API中转平台转发功能正常！Anthropic接口测试通过。'
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

    # 流式响应支持
    if body.get('stream', False):
        def generate():
            events = [
                {'type': 'message_start', 'message': {'id': response_data['id'], 'type': 'message', 'role': 'assistant', 'content': [], 'model': model, 'stop_reason': None, 'stop_sequence': None, 'usage': {'input_tokens': 10, 'output_tokens': 0}}},
                {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'thinking', 'thinking': '', 'signature': ''}},
            ]

            # thinking 流式
            thinking_text = '这是Mock服务器模拟的thinking过程。Anthropic的thinking块展示了模型的推理过程，用于验证thinking功能是否正常转发。'
            for char in thinking_text:
                events.append({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'thinking_delta', 'thinking': char}})

            events.append({'type': 'content_block_stop', 'index': 0})
            events.append({'type': 'content_block_start', 'index': 1, 'content_block': {'type': 'text', 'text': ''}})

            # text 流式
            text_content = '这是一个Mock服务器返回的固定结论内容。你的API中转平台转发功能正常！Anthropic接口测试通过。'
            for char in text_content:
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


@app.route('/logs', methods=['GET'])
def api_get_logs():
    """获取请求日志"""
    logs = get_logs()
    return jsonify({'count': len(logs), 'logs': logs})


@app.route('/logs/clear', methods=['POST'])
def api_clear_logs():
    """清空请求日志"""
    clear_logs()
    return jsonify({'status': 'ok', 'message': '日志已清空'})


@app.route('/health', methods=['GET'])
def health():
    """健康检查"""
    return jsonify({'status': 'running', 'log_count': len(get_logs())})


def run_server(port=12312, debug=False):
    """启动Flask服务器"""
    app.run(host='127.0.0.1', port=port, debug=debug, threaded=True)


if __name__ == '__main__':
    print("=" * 60)
    print("API Mock Server 启动中...")
    print("=" * 60)
    print(f"OpenAI 接口:    http://localhost:12312/openai/v1/chat/completions")
    print(f"Anthropic 接口: http://localhost:12312/anthropic/v1/messages")
    print(f"日志查询:       http://localhost:12312/logs")
    print(f"健康检查:       http://localhost:12312/health")
    print("=" * 60)
    run_server()
