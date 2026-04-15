#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
API Mock Server GUI - 本地大模型接口模拟服务器（带图形界面）
"""

import json
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
from datetime import datetime

from mock_server import run_server, get_logs, clear_logs


class MockServerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("API Mock Server - 本地接口模拟器")
        self.root.geometry("1100x700")
        self.root.minsize(900, 600)

        # 设置样式
        style = ttk.Style()
        style.theme_use('clam')

        # 创建主框架
        self.main_frame = ttk.Frame(root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # 顶部控制面板
        self.create_control_panel()

        # 分隔线
        ttk.Separator(self.main_frame, orient='horizontal').pack(fill='x', pady=10)

        # 日志列表
        self.create_log_panel()

        # 详情面板
        self.create_detail_panel()

        # 启动服务器
        self.start_server()

        # 定时刷新日志
        self.refresh_logs()

    def create_control_panel(self):
        """控制面板"""
        control_frame = ttk.Frame(self.main_frame)
        control_frame.pack(fill='x')

        # 标题
        title_label = ttk.Label(control_frame, text="API Mock Server", font=('Microsoft YaHei', 16, 'bold'))
        title_label.pack(side='left')

        # 状态指示
        self.status_var = tk.StringVar(value="● 运行中")
        status_label = ttk.Label(control_frame, textvariable=self.status_var, foreground='green', font=('Microsoft YaHei', 10))
        status_label.pack(side='left', padx=20)

        # 日志计数
        self.log_count_var = tk.StringVar(value="请求数: 0")
        count_label = ttk.Label(control_frame, textvariable=self.log_count_var, font=('Microsoft YaHei', 10))
        count_label.pack(side='left', padx=10)

        # 按钮区域
        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(side='right')

        refresh_btn = ttk.Button(btn_frame, text="刷新日志", command=self.on_refresh)
        refresh_btn.pack(side='left', padx=5)

        clear_btn = ttk.Button(btn_frame, text="清空日志", command=self.on_clear)
        clear_btn.pack(side='left', padx=5)

        # 接口信息
        info_frame = ttk.Frame(self.main_frame)
        info_frame.pack(fill='x', pady=(5, 0))

        info_text = (
            "OpenAI 接口:    http://localhost:12312/openai/v1/chat/completions\n"
            "Anthropic 接口: http://localhost:12312/anthropic/v1/messages\n"
            "日志 API:       http://localhost:12312/logs"
        )
        info_label = ttk.Label(info_frame, text=info_text, font=('Consolas', 9), foreground='#666666')
        info_label.pack(anchor='w')

    def create_log_panel(self):
        """日志列表面板"""
        log_frame = ttk.LabelFrame(self.main_frame, text="请求日志", padding="5")
        log_frame.pack(fill='both', expand=True, pady=(5, 0))

        # 创建Treeview
        columns = ('时间', '类型', '模型', '客户端IP', 'User-Agent', '路径')
        self.tree = ttk.Treeview(log_frame, columns=columns, show='headings', height=12)

        # 设置列
        col_widths = {'时间': 150, '类型': 80, '模型': 150, '客户端IP': 120, 'User-Agent': 300, '路径': 200}
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=col_widths.get(col, 100), minwidth=50)

        # 滚动条
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # 绑定选择事件
        self.tree.bind('<<TreeviewSelect>>', self.on_log_select)
        self.tree.bind('<Double-1>', self.on_log_double_click)

    def create_detail_panel(self):
        """详情面板"""
        detail_frame = ttk.LabelFrame(self.main_frame, text="请求详情", padding="5")
        detail_frame.pack(fill='both', expand=True, pady=(5, 0))

        # 创建Notebook用于切换标签页
        self.notebook = ttk.Notebook(detail_frame)
        self.notebook.pack(fill='both', expand=True)

        # Headers 标签页
        headers_frame = ttk.Frame(self.notebook)
        self.headers_text = scrolledtext.ScrolledText(headers_frame, wrap=tk.WORD, height=8, font=('Consolas', 9))
        self.headers_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.notebook.add(headers_frame, text='请求 Headers')

        # Body 标签页
        body_frame = ttk.Frame(self.notebook)
        self.body_text = scrolledtext.ScrolledText(body_frame, wrap=tk.WORD, height=8, font=('Consolas', 9))
        self.body_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.notebook.add(body_frame, text='请求 Body')

    def start_server(self):
        """启动服务器"""
        def run():
            try:
                run_server(port=12312, debug=False)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", f"服务器启动失败: {e}"))
                self.status_var.set("● 启动失败")

        server_thread = threading.Thread(target=run, daemon=True)
        server_thread.start()

    def refresh_logs(self):
        """定时刷新日志"""
        try:
            logs = get_logs()
            self.log_count_var.set(f"请求数: {len(logs)}")

            # 清空现有数据
            for item in self.tree.get_children():
                self.tree.delete(item)

            # 添加日志条目
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

        # 每2秒刷新一次
        self.root.after(2000, self.refresh_logs)

    def on_refresh(self):
        """手动刷新"""
        self.refresh_logs()

    def on_clear(self):
        """清空日志"""
        if messagebox.askyesno("确认", "确定要清空所有日志吗？"):
            clear_logs()
            self.refresh_logs()

    def on_log_select(self, event):
        """选择日志条目时显示详情"""
        selection = self.tree.selection()
        if not selection:
            return

        item = self.tree.item(selection[0])
        log_id = item['tags'][0] if item['tags'] else None

        if log_id:
            logs = get_logs()
            log = next((l for l in logs if l.get('id') == log_id), None)
            if log:
                # 显示 headers
                headers = log.get('headers', {})
                headers_str = json.dumps(headers, indent=2, ensure_ascii=False)
                self.headers_text.delete(1.0, tk.END)
                self.headers_text.insert(tk.END, headers_str)

                # 显示 body
                body = log.get('body', {})
                body_str = json.dumps(body, indent=2, ensure_ascii=False)
                self.body_text.delete(1.0, tk.END)
                self.body_text.insert(tk.END, body_str)

    def on_log_double_click(self, event):
        """双击日志条目"""
        selection = self.tree.selection()
        if selection:
            self.on_log_select(event)


def main():
    root = tk.Tk()
    app = MockServerGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
