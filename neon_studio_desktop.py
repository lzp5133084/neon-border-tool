# -*- coding: utf-8 -*-
"""
霓虹边框凸显工具 - 桌面版
Neon Studio Desktop v1.0.0
作者：军哥懂保
微信：xunijiayuan
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from PIL import Image, ImageDraw, ImageTk, ImageFilter, ImageFont
import os
import json
import datetime
import sqlite3
import sys

APP_NAME = "霓虹边框凸显工具"
APP_VERSION = "1.0.0"
AUTHOR = "军哥懂保"
WECHAT = "xunijiayuan"
PHONE = "18180309010"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
UPLOAD_DIR = os.path.join(DATA_DIR, 'uploads')
OUTPUT_DIR = os.path.join(DATA_DIR, 'outputs')
DB_PATH = os.path.join(DATA_DIR, 'neon_desktop.db')

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

COLOR_PRESETS = [
    ("电光蓝", "#00ffff"),
    ("粉紫", "#ff00ff"),
    ("青绿", "#00ff88"),
    ("橙黄", "#ff6600"),
    ("玫红", "#ff0066"),
    ("纯白", "#ffffff"),
]

DEFAULT_TEMPLATES = [
    {"name": "赛博蓝光 · 人物背部", "category": "人物", "color": "#00ffff", "thickness": 4, "glow": 20, "darken": 15, "is_default": True},
    {"name": "粉紫渐变 · 通用物体", "category": "通用", "color": "#ff00ff", "thickness": 3, "glow": 15, "darken": 10, "is_default": True},
    {"name": "青绿色赛博风", "category": "赛博", "color": "#00ff88", "thickness": 5, "glow": 25, "darken": 20, "is_default": True},
    {"name": "纯白冷光 · 极简风", "category": "极简", "color": "#ffffff", "thickness": 2, "glow": 12, "darken": 5, "is_default": True},
    {"name": "玫红霓虹 · 高亮", "category": "高亮", "color": "#ff0066", "thickness": 4, "glow": 30, "darken": 25, "is_default": True},
]


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mode TEXT DEFAULT 'manual',
            original_image TEXT,
            output_image TEXT,
            target_description TEXT,
            neon_color TEXT,
            neon_thickness INTEGER,
            glow_intensity INTEGER,
            background_darken INTEGER,
            created_at TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            category TEXT,
            neon_color TEXT,
            neon_thickness INTEGER,
            glow_intensity INTEGER,
            background_darken INTEGER,
            is_default INTEGER DEFAULT 0,
            created_at TEXT
        )
    ''')
    
    cursor.execute('SELECT COUNT(*) FROM templates')
    if cursor.fetchone()[0] == 0:
        now = datetime.datetime.now().isoformat()
        for tpl in DEFAULT_TEMPLATES:
            cursor.execute('''
                INSERT INTO templates (name, category, neon_color, neon_thickness, glow_intensity, background_darken, is_default, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (tpl["name"], tpl["category"], tpl["color"], tpl["thickness"], tpl["glow"], tpl["darken"], 1 if tpl["is_default"] else 0, now))
    
    conn.commit()
    conn.close()


class NeonStudioApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry("1280x800")
        self.root.minsize(1000, 650)
        
        self.original_image = None
        self.display_image = None
        self.photo_image = None
        self.shapes = []
        self.current_tool = "freehand"
        self.neon_color = "#00ffff"
        self.neon_thickness = 4
        self.glow_intensity = 20
        self.background_darken = 0
        self.is_drawing = False
        self.last_x = 0
        self.last_y = 0
        self.start_x = 0
        self.start_y = 0
        self.temp_shape = None
        self.scale_factor = 1.0
        
        self.setup_style()
        init_db()
        self.create_ui()
    
    def setup_style(self):
        self.style = ttk.Style()
        try:
            self.style.theme_use('clam')
        except:
            pass
        
        self.bg_color = "#0d1321"
        self.card_color = "#141b2d"
        self.sidebar_color = "#111827"
        self.text_color = "#e2e8f0"
        self.text_secondary = "#94a3b8"
        self.accent_color = "#06b6d4"
        self.primary_color = "#6366f1"
        self.border_color = "#1e293b"
        
        self.root.configure(bg=self.bg_color)
        
        self.style.configure('TFrame', background=self.bg_color)
        self.style.configure('Card.TFrame', background=self.card_color)
        self.style.configure('Sidebar.TFrame', background=self.sidebar_color)
        
        self.style.configure('TLabel', background=self.bg_color, foreground=self.text_color, font=('Microsoft YaHei', 10))
        self.style.configure('Card.TLabel', background=self.card_color, foreground=self.text_color)
        self.style.configure('Sidebar.TLabel', background=self.sidebar_color, foreground=self.text_color)
        self.style.configure('Title.TLabel', background=self.sidebar_color, foreground=self.text_color, font=('Microsoft YaHei', 14, 'bold'))
        self.style.configure('Subtitle.TLabel', background=self.sidebar_color, foreground=self.text_secondary, font=('Microsoft YaHei', 9))
        self.style.configure('Section.TLabel', background=self.card_color, foreground=self.text_color, font=('Microsoft YaHei', 11, 'bold'))
        self.style.configure('Info.TLabel', background=self.card_color, foreground=self.text_secondary, font=('Microsoft YaHei', 9))
        self.style.configure('StatValue.TLabel', background=self.card_color, foreground=self.accent_color, font=('Microsoft YaHei', 20, 'bold'))
        
        self.style.configure('TButton', font=('Microsoft YaHei', 9), padding=8, background=self.card_color, foreground=self.text_color)
        self.style.map('TButton', background=[('active', self.primary_color), ('pressed', self.primary_color)])
        
        self.style.configure('Primary.TButton', font=('Microsoft YaHei', 10, 'bold'), padding=10, background=self.primary_color, foreground='white')
        self.style.map('Primary.TButton', background=[('active', '#4f46e5')])
        
        self.style.configure('Danger.TButton', font=('Microsoft YaHei', 9), padding=8, background='#ef4444', foreground='white')
        self.style.configure('Success.TButton', font=('Microsoft YaHei', 9), padding=8, background='#10b981', foreground='white')
        
        self.style.configure('TNotebook', background=self.bg_color, borderwidth=0)
        self.style.configure('TNotebook.Tab', padding=[15, 10], background=self.card_color, foreground=self.text_secondary, font=('Microsoft YaHei', 10))
        self.style.map('TNotebook.Tab', background=[('selected', self.primary_color), ('active', self.card_color)], foreground=[('selected', 'white')])
        
        self.style.configure('TScale', background=self.card_color)
        self.style.configure('Horizontal.TScale', background=self.card_color)
        
        self.style.configure('TEntry', fieldbackground='#0a0e1a', foreground=self.text_color, insertcolor=self.text_color)
        self.style.configure('TCombobox', fieldbackground=self.card_color, foreground=self.text_color)
        
        self.style.configure('Tool.TButton', font=('Microsoft YaHei', 9), padding=6, width=8, background=self.card_color, foreground=self.text_color)
        self.style.map('Tool.TButton', background=[('active', self.primary_color), ('pressed', self.primary_color)])
        
        self.style.configure('Color.TButton', padding=4, width=4)
    
    def create_ui(self):
        main_frame = ttk.Frame(self.root, style='TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        sidebar = tk.Frame(main_frame, bg=self.sidebar_color, width=220)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)
        
        logo_frame = tk.Frame(sidebar, bg=self.sidebar_color)
        logo_frame.pack(pady=20, padx=15)
        
        tk.Label(logo_frame, text="⚡ 霓虹工坊", font=('Microsoft YaHei', 16, 'bold'), 
                fg="#8b5cf6", bg=self.sidebar_color).pack()
        tk.Label(logo_frame, text=f"NEON STUDIO v{APP_VERSION}", font=('Microsoft YaHei', 8), 
                fg=self.text_secondary, bg=self.sidebar_color).pack(pady=(2, 0))
        
        tk.Frame(sidebar, bg=self.border_color, height=1).pack(fill=tk.X, padx=15, pady=10)
        
        nav_items = [
            ("🎨 手动绘制", "manual"),
            ("✨ AI智能生成", "ai"),
            ("📚 模板库", "templates"),
            ("📋 历史记录", "history"),
            ("ℹ️ 关于程序", "about"),
        ]
        
        self.nav_buttons = {}
        for text, page in nav_items:
            btn = tk.Button(sidebar, text=text, font=('Microsoft YaHei', 10), 
                           bg=self.sidebar_color, fg=self.text_secondary,
                           activebackground=self.primary_color, activeforeground='white',
                           bd=0, padx=15, pady=10, anchor='w', cursor='hand2',
                           command=lambda p=page: self.switch_page(p))
            btn.pack(fill=tk.X, padx=5)
            self.nav_buttons[page] = btn
        
        tk.Frame(sidebar, bg=self.border_color, height=1).pack(fill=tk.X, padx=15, pady=10)
        
        info_frame = tk.Frame(sidebar, bg=self.sidebar_color)
        info_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=15, pady=15)
        
        tk.Label(info_frame, text=f"作者：{AUTHOR}", font=('Microsoft YaHei', 9), 
                fg=self.text_secondary, bg=self.sidebar_color).pack(anchor='w', pady=2)
        tk.Label(info_frame, text=f"微信：{WECHAT}", font=('Microsoft YaHei', 9), 
                fg=self.text_secondary, bg=self.sidebar_color).pack(anchor='w', pady=2)
        tk.Label(info_frame, text=f"电话：{PHONE}", font=('Microsoft YaHei', 9), 
                fg=self.text_secondary, bg=self.sidebar_color).pack(anchor='w', pady=2)
        
        self.content_frame = tk.Frame(main_frame, bg=self.bg_color)
        self.content_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.pages = {}
        self.create_manual_page()
        self.create_ai_page()
        self.create_templates_page()
        self.create_history_page()
        self.create_about_page()
        
        self.switch_page('manual')
    
    def switch_page(self, page):
        for p in self.pages.values():
            p.pack_forget()
        if page in self.pages:
            self.pages[page].pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        for p, btn in self.nav_buttons.items():
            if p == page:
                btn.configure(bg=self.primary_color, fg='white')
            else:
                btn.configure(bg=self.sidebar_color, fg=self.text_secondary)
    
    def create_manual_page(self):
        page = tk.Frame(self.content_frame, bg=self.bg_color)
        self.pages['manual'] = page
        
        top_card = tk.Frame(page, bg=self.card_color, bd=0, highlightthickness=1, highlightbackground=self.border_color)
        top_card.pack(fill=tk.X, pady=(0, 15))
        top_card.configure(highlightbackground=self.border_color)
        
        tk.Label(top_card, text="📤 上传图片", font=('Microsoft YaHei', 12, 'bold'), 
                fg=self.text_color, bg=self.card_color).pack(side=tk.LEFT, padx=15, pady=12)
        
        ttk.Button(top_card, text="打开图片", style='Primary.TButton', 
                  command=self.open_image).pack(side=tk.RIGHT, padx=15, pady=10)
        
        main_container = tk.Frame(page, bg=self.bg_color)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        canvas_frame = tk.Frame(main_container, bg=self.card_color, bd=0, highlightthickness=1, highlightbackground=self.border_color)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 15))
        
        tk.Label(canvas_frame, text="🖼️ 图片预览", font=('Microsoft YaHei', 11, 'bold'), 
                fg=self.text_color, bg=self.card_color).pack(anchor='w', padx=15, pady=10)
        
        self.canvas_container = tk.Frame(canvas_frame, bg='#0a0e1a')
        self.canvas_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        
        self.canvas = tk.Canvas(self.canvas_container, bg='#0a0e1a', highlightthickness=0, cursor='crosshair')
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.canvas.bind("<Button-1>", self.start_drawing)
        self.canvas.bind("<B1-Motion>", self.draw)
        self.canvas.bind("<ButtonRelease-1>", self.stop_drawing)
        
        btn_bar = tk.Frame(canvas_frame, bg=self.card_color)
        btn_bar.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        ttk.Button(btn_bar, text="🔄 重置", command=self.reset_canvas).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_bar, text="↩️ 撤销", command=self.undo_shape).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_bar, text="💾 保存图片", style='Success.TButton', 
                  command=self.save_image).pack(side=tk.RIGHT)
        
        panel_frame = tk.Frame(main_container, bg=self.bg_color, width=300)
        panel_frame.pack(side=tk.RIGHT, fill=tk.Y)
        panel_frame.pack_propagate(False)
        
        tools_card = tk.Frame(panel_frame, bg=self.card_color, bd=0, highlightthickness=1, highlightbackground=self.border_color)
        tools_card.pack(fill=tk.X, pady=(0, 15))
        
        tk.Label(tools_card, text="🛠️ 绘制工具", font=('Microsoft YaHei', 11, 'bold'), 
                fg=self.text_color, bg=self.card_color).pack(anchor='w', padx=15, pady=10)
        
        tools_grid = tk.Frame(tools_card, bg=self.card_color)
        tools_grid.pack(padx=15, pady=(0, 15))
        
        self.tool_buttons = {}
        tools = [
            ("✏️ 自由绘制", "freehand"),
            ("⬜ 矩形", "rect"),
            ("⭕ 椭圆", "ellipse"),
            ("🧹 橡皮擦", "eraser"),
        ]
        
        for i, (text, tool) in enumerate(tools):
            row = i // 2
            col = i % 2
            btn = tk.Button(tools_grid, text=text, font=('Microsoft YaHei', 9),
                           bg=self.card_color, fg=self.text_secondary,
                           activebackground=self.primary_color, activeforeground='white',
                           bd=1, relief='solid', cursor='hand2',
                           command=lambda t=tool: self.set_tool(t), width=12, height=2)
            btn.grid(row=row, column=col, padx=4, pady=4, sticky='nsew')
            self.tool_buttons[tool] = btn
        
        self.set_tool('freehand')
        
        color_card = tk.Frame(panel_frame, bg=self.card_color, bd=0, highlightthickness=1, highlightbackground=self.border_color)
        color_card.pack(fill=tk.X, pady=(0, 15))
        
        tk.Label(color_card, text="🌈 霓虹颜色", font=('Microsoft YaHei', 11, 'bold'), 
                fg=self.text_color, bg=self.card_color).pack(anchor='w', padx=15, pady=10)
        
        color_grid = tk.Frame(color_card, bg=self.card_color)
        color_grid.pack(padx=15, pady=(0, 15))
        
        self.color_buttons = {}
        for i, (name, color) in enumerate(COLOR_PRESETS):
            row = i // 3
            col = i % 3
            btn = tk.Button(color_grid, text=name, font=('Microsoft YaHei', 8),
                           bg=color, fg='black' if color == '#ffffff' else 'white',
                           activebackground=color, activeforeground='white',
                           bd=3, relief='solid', cursor='hand2',
                           command=lambda c=color: self.set_color(c), width=8, height=2)
            btn.grid(row=row, column=col, padx=4, pady=4)
            self.color_buttons[color] = btn
        
        custom_btn = tk.Button(color_grid, text="🎨 自定义", font=('Microsoft YaHei', 8),
                              bg=self.card_color, fg=self.text_color,
                              activebackground=self.card_color, activeforeground=self.text_color,
                              bd=1, relief='ridge', cursor='hand2',
                              command=self.choose_custom_color, width=8, height=2)
        custom_btn.grid(row=2, column=0, columnspan=3, padx=4, pady=4, sticky='ew')
        
        self.set_color("#00ffff")
        
        params_card = tk.Frame(panel_frame, bg=self.card_color, bd=0, highlightthickness=1, highlightbackground=self.border_color)
        params_card.pack(fill=tk.X, pady=(0, 15))
        
        tk.Label(params_card, text="⚙️ 参数调节", font=('Microsoft YaHei', 11, 'bold'), 
                fg=self.text_color, bg=self.card_color).pack(anchor='w', padx=15, pady=10)
        
        params_inner = tk.Frame(params_card, bg=self.card_color)
        params_inner.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        tk.Label(params_inner, text="边框粗细", font=('Microsoft YaHei', 9),
                fg=self.text_secondary, bg=self.card_color).pack(anchor='w')
        self.thickness_var = tk.IntVar(value=4)
        thickness_frame = tk.Frame(params_inner, bg=self.card_color)
        thickness_frame.pack(fill=tk.X, pady=(2, 10))
        tk.Scale(thickness_frame, from_=1, to=20, orient=tk.HORIZONTAL, 
                variable=self.thickness_var, bg=self.card_color, fg=self.accent_color,
                troughcolor=self.border_color, highlightthickness=0,
                command=self.update_thickness).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.thickness_label = tk.Label(thickness_frame, text="4px", font=('Microsoft YaHei', 9, 'bold'),
                                         fg=self.accent_color, bg=self.card_color, width=6)
        self.thickness_label.pack(side=tk.RIGHT, padx=(10, 0))
        
        tk.Label(params_inner, text="光晕强度", font=('Microsoft YaHei', 9),
                fg=self.text_secondary, bg=self.card_color).pack(anchor='w')
        self.glow_var = tk.IntVar(value=20)
        glow_frame = tk.Frame(params_inner, bg=self.card_color)
        glow_frame.pack(fill=tk.X, pady=(2, 10))
        tk.Scale(glow_frame, from_=0, to=50, orient=tk.HORIZONTAL, 
                variable=self.glow_var, bg=self.card_color, fg=self.accent_color,
                troughcolor=self.border_color, highlightthickness=0,
                command=self.update_glow).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.glow_label = tk.Label(glow_frame, text="20", font=('Microsoft YaHei', 9, 'bold'),
                                   fg=self.accent_color, bg=self.card_color, width=6)
        self.glow_label.pack(side=tk.RIGHT, padx=(10, 0))
        
        tk.Label(params_inner, text="背景压暗", font=('Microsoft YaHei', 9),
                fg=self.text_secondary, bg=self.card_color).pack(anchor='w')
        self.darken_var = tk.IntVar(value=0)
        darken_frame = tk.Frame(params_inner, bg=self.card_color)
        darken_frame.pack(fill=tk.X, pady=(2, 0))
        tk.Scale(darken_frame, from_=0, to=70, orient=tk.HORIZONTAL, 
                variable=self.darken_var, bg=self.card_color, fg=self.accent_color,
                troughcolor=self.border_color, highlightthickness=0,
                command=self.update_darken).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.darken_label = tk.Label(darken_frame, text="0%", font=('Microsoft YaHei', 9, 'bold'),
                                     fg=self.accent_color, bg=self.card_color, width=6)
        self.darken_label.pack(side=tk.RIGHT, padx=(10, 0))
        
        desc_card = tk.Frame(panel_frame, bg=self.card_color, bd=0, highlightthickness=1, highlightbackground=self.border_color)
        desc_card.pack(fill=tk.X)
        
        tk.Label(desc_card, text="📝 目标描述（可选）", font=('Microsoft YaHei', 11, 'bold'), 
                fg=self.text_color, bg=self.card_color).pack(anchor='w', padx=15, pady=10)
        
        self.target_desc = tk.Text(desc_card, height=3, bg='#0a0e1a', fg=self.text_color,
                                   insertbackground=self.text_color, bd=1, relief='solid',
                                   font=('Microsoft YaHei', 9))
        self.target_desc.pack(fill=tk.X, padx=15, pady=(0, 15))
        self.target_desc.insert('1.0', '')
    
    def create_ai_page(self):
        page = tk.Frame(self.content_frame, bg=self.bg_color)
        self.pages['ai'] = page
        
        card = tk.Frame(page, bg=self.card_color, bd=0, highlightthickness=1, highlightbackground=self.border_color)
        card.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(card, text="✨ AI智能霓虹生成", font=('Microsoft YaHei', 14, 'bold'), 
                fg=self.text_color, bg=self.card_color).pack(anchor='w', padx=20, pady=15)
        
        tip_frame = tk.Frame(card, bg='#0d2833')
        tip_frame.pack(fill=tk.X, padx=20, pady=(0, 15))
        tk.Label(tip_frame, text="💡 提示：AI生成需要调用火山引擎豆包API，请先在系统设置中配置API Key。\n推荐使用「手动绘制」模式，效果实时可见更可控！", 
                font=('Microsoft YaHei', 9), fg=self.accent_color, bg='#0d2833',
                justify=tk.LEFT).pack(padx=15, pady=10, anchor='w')
        
        center_frame = tk.Frame(card, bg=self.card_color)
        center_frame.pack(expand=True)
        
        tk.Label(center_frame, text="🚧 AI功能开发中...", font=('Microsoft YaHei', 16, 'bold'), 
                fg=self.text_secondary, bg=self.card_color).pack(pady=10)
        tk.Label(center_frame, text="可使用手动绘制模式实现霓虹边框效果", 
                font=('Microsoft YaHei', 10), fg=self.text_secondary, bg=self.card_color).pack()
        
        ttk.Button(center_frame, text="切换到手动绘制", style='Primary.TButton',
                  command=lambda: self.switch_page('manual')).pack(pady=20)
    
    def create_templates_page(self):
        page = tk.Frame(self.content_frame, bg=self.bg_color)
        self.pages['templates'] = page
        
        card = tk.Frame(page, bg=self.card_color, bd=0, highlightthickness=1, highlightbackground=self.border_color)
        card.pack(fill=tk.BOTH, expand=True)
        
        header = tk.Frame(card, bg=self.card_color)
        header.pack(fill=tk.X, padx=20, pady=15)
        tk.Label(header, text="📚 霓虹效果模板库", font=('Microsoft YaHei', 14, 'bold'), 
                fg=self.text_color, bg=self.card_color).pack(side=tk.LEFT)
        ttk.Button(header, text="🔄 刷新", command=self.refresh_templates).pack(side=tk.RIGHT)
        
        self.templates_canvas = tk.Canvas(card, bg=self.card_color, highlightthickness=0)
        self.templates_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(20, 0), pady=(0, 20))
        
        scrollbar = ttk.Scrollbar(card, orient="vertical", command=self.templates_canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 20), pady=(0, 20))
        
        self.templates_canvas.configure(yscrollcommand=scrollbar.set)
        
        self.templates_inner = tk.Frame(self.templates_canvas, bg=self.card_color)
        self.templates_canvas.create_window((0, 0), window=self.templates_inner, anchor="nw")
        
        self.templates_inner.bind("<Configure>", lambda e: self.templates_canvas.configure(scrollregion=self.templates_canvas.bbox("all")))
        
        self.refresh_templates()
    
    def refresh_templates(self):
        for widget in self.templates_inner.winfo_children():
            widget.destroy()
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM templates ORDER BY id ASC')
        templates = cursor.fetchall()
        conn.close()
        
        columns = 3
        for i, tpl in enumerate(templates):
            row = i // columns
            col = i % columns
            
            tpl_id, name, category, color, thickness, glow, darken, is_default, created_at = tpl
            
            card = tk.Frame(self.templates_inner, bg='#1a1f35', 
                           bd=1, relief='solid', highlightbackground=self.border_color)
            card.grid(row=row, column=col, padx=8, pady=8, sticky='nsew')
            card.configure(highlightbackground=self.border_color)
            
            preview = tk.Canvas(card, height=70, bg=self.card_color, highlightthickness=0)
            preview.pack(fill=tk.X)
            
            preview.create_rectangle(60, 15, 160, 55, outline=color, width=3)
            preview.create_oval(70, 20, 150, 50, outline=color, width=2)
            
            badge = tk.Label(card, text=category, font=('Microsoft YaHei', 8),
                            fg=self.accent_color, bg='#22304a')
            badge.pack(anchor='w', padx=10, pady=(8, 4))
            
            tk.Label(card, text=name, font=('Microsoft YaHei', 10, 'bold'),
                    fg=self.text_color, bg='#1a1f35').pack(anchor='w', padx=10)
            
            info = f"粗细:{thickness}px | 光晕:{glow} | 压暗:{darken}%"
            tk.Label(card, text=info, font=('Microsoft YaHei', 8),
                    fg=self.text_secondary, bg='#1a1f35').pack(anchor='w', padx=10, pady=(2, 8))
            
            btn_frame = tk.Frame(card, bg='#1a1f35')
            btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
            
            tk.Button(btn_frame, text="使用", font=('Microsoft YaHei', 9),
                     bg=self.primary_color, fg='white', activebackground='#4f46e5',
                     activeforeground='white', bd=0, cursor='hand2',
                     command=lambda t=tpl: self.apply_template(t)).pack(side=tk.LEFT, fill=tk.X, expand=True)
            
            if not is_default:
                tk.Button(btn_frame, text="删除", font=('Microsoft YaHei', 9),
                         bg='#ef4444', fg='white', activebackground='#dc2626',
                         activeforeground='white', bd=0, cursor='hand2',
                         command=lambda tid=tpl_id: self.delete_template(tid)).pack(side=tk.RIGHT, padx=(5, 0))
        
        for i in range(columns):
            self.templates_inner.grid_columnconfigure(i, weight=1, uniform='col')
    
    def apply_template(self, tpl):
        tpl_id, name, category, color, thickness, glow, darken, is_default, created_at = tpl
        
        self.set_color(color)
        self.thickness_var.set(thickness)
        self.neon_thickness = thickness
        self.thickness_label.config(text=f"{thickness}px")
        
        self.glow_var.set(glow)
        self.glow_intensity = glow
        self.glow_label.config(text=str(glow))
        
        self.darken_var.set(darken)
        self.background_darken = darken
        self.darken_label.config(text=f"{darken}%")
        
        self.switch_page('manual')
        self.show_info(f"已应用模板：{name}")
    
    def delete_template(self, tpl_id):
        if not messagebox.askyesno("确认", "确定要删除这个模板吗？"):
            return
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM templates WHERE id = ?', (tpl_id,))
        conn.commit()
        conn.close()
        self.refresh_templates()
        self.show_info("模板已删除")
    
    def create_history_page(self):
        page = tk.Frame(self.content_frame, bg=self.bg_color)
        self.pages['history'] = page
        
        stats_frame = tk.Frame(page, bg=self.bg_color)
        stats_frame.pack(fill=tk.X, pady=(0, 15))
        
        stats = [
            ("📊 总处理数", "total"),
            ("🎨 手动绘制", "manual"),
            ("✨ AI生成", "ai"),
            ("📚 模板数量", "templates"),
        ]
        
        self.stat_labels = {}
        for i, (label, key) in enumerate(stats):
            card = tk.Frame(stats_frame, bg=self.card_color, bd=0, highlightthickness=1, highlightbackground=self.border_color)
            card.grid(row=0, column=i, padx=(0 if i == 0 else 10, 0), sticky='nsew', ipadx=10, ipady=10)
            stats_frame.grid_columnconfigure(i, weight=1)
            
            tk.Label(card, text=label, font=('Microsoft YaHei', 9),
                    fg=self.text_secondary, bg=self.card_color).pack(anchor='w', padx=15, pady=(10, 0))
            val_label = tk.Label(card, text="0", font=('Microsoft YaHei', 22, 'bold'),
                               fg=self.accent_color, bg=self.card_color)
            val_label.pack(anchor='w', padx=15, pady=(2, 10))
            self.stat_labels[key] = val_label
        
        card = tk.Frame(page, bg=self.card_color, bd=0, highlightthickness=1, highlightbackground=self.border_color)
        card.pack(fill=tk.BOTH, expand=True)
        
        header = tk.Frame(card, bg=self.card_color)
        header.pack(fill=tk.X, padx=20, pady=15)
        tk.Label(header, text="📋 处理历史", font=('Microsoft YaHei', 14, 'bold'), 
                fg=self.text_color, bg=self.card_color).pack(side=tk.LEFT)
        
        filter_frame = tk.Frame(header, bg=self.card_color)
        filter_frame.pack(side=tk.RIGHT)
        
        self.history_filter = tk.StringVar(value="")
        filter_combo = ttk.Combobox(filter_frame, textvariable=self.history_filter, 
                                    values=["", "manual", "ai"], width=12, state='readonly')
        filter_combo.pack(side=tk.RIGHT)
        filter_combo.bind('<<ComboboxSelected>>', lambda e: self.refresh_history())
        
        tk.Label(filter_frame, text="筛选：", font=('Microsoft YaHei', 9),
                fg=self.text_secondary, bg=self.card_color).pack(side=tk.RIGHT, padx=(0, 8))
        
        self.history_tree_frame = tk.Frame(card, bg=self.card_color)
        self.history_tree_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
        
        self.refresh_history()
    
    def refresh_history(self):
        for widget in self.history_tree_frame.winfo_children():
            widget.destroy()
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        mode_filter = self.history_filter.get()
        if mode_filter:
            cursor.execute('SELECT * FROM records WHERE mode = ? ORDER BY id DESC LIMIT 50', (mode_filter,))
        else:
            cursor.execute('SELECT * FROM records ORDER BY id DESC LIMIT 50')
        
        records = cursor.fetchall()
        
        cursor.execute('SELECT COUNT(*) FROM records')
        total = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM records WHERE mode = "manual"')
        manual_count = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM records WHERE mode = "ai"')
        ai_count = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM templates')
        tpl_count = cursor.fetchone()[0]
        
        conn.close()
        
        self.stat_labels['total'].config(text=str(total))
        self.stat_labels['manual'].config(text=str(manual_count))
        self.stat_labels['ai'].config(text=str(ai_count))
        self.stat_labels['templates'].config(text=str(tpl_count))
        
        columns = ('id', 'mode', 'target', 'color', 'created_at')
        tree = ttk.Treeview(self.history_tree_frame, columns=columns, show='headings', height=10)
        
        tree.heading('id', text='ID')
        tree.heading('mode', text='模式')
        tree.heading('target', text='目标描述')
        tree.heading('color', text='霓虹颜色')
        tree.heading('created_at', text='创建时间')
        
        tree.column('id', width=60, anchor='center')
        tree.column('mode', width=100, anchor='center')
        tree.column('target', width=250, anchor='w')
        tree.column('color', width=100, anchor='center')
        tree.column('created_at', width=180, anchor='center')
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(self.history_tree_frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree.configure(yscrollcommand=scrollbar.set)
        
        for rec in records:
            rid, mode, orig, output, target, color, thickness, glow, darken, created_at = rec
            mode_text = "手动绘制" if mode == "manual" else "AI生成"
            tree.insert('', 'end', values=(rid, mode_text, target or '-', color, created_at))
        
        tree.bind('<Double-1>', lambda e: self.view_record(tree))
    
    def view_record(self, tree):
        selection = tree.selection()
        if not selection:
            return
        item = tree.item(selection[0])
        rid = item['values'][0]
        messagebox.showinfo("记录详情", f"记录ID: {rid}\n\n详细功能开发中...")
    
    def create_about_page(self):
        page = tk.Frame(self.content_frame, bg=self.bg_color)
        self.pages['about'] = page
        
        card = tk.Frame(page, bg=self.card_color, bd=0, highlightthickness=1, highlightbackground=self.border_color)
        card.pack(fill=tk.BOTH, expand=True)
        
        center_frame = tk.Frame(card, bg=self.card_color)
        center_frame.pack(expand=True)
        
        logo_frame = tk.Frame(center_frame, bg='', width=100, height=100)
        logo_frame.pack(pady=(20, 15))
        
        logo_canvas = tk.Canvas(logo_frame, width=100, height=100, bg=self.card_color, highlightthickness=0)
        logo_canvas.pack()
        logo_canvas.create_rectangle(10, 10, 90, 90, fill='', outline=self.primary_color, width=4)
        logo_canvas.create_text(50, 50, text="⚡", font=('Arial', 36, 'bold'), fill=self.accent_color)
        
        tk.Label(center_frame, text=APP_NAME, font=('Microsoft YaHei', 20, 'bold'), 
                fg=self.text_color, bg=self.card_color).pack()
        tk.Label(center_frame, text=f"版本 v{APP_VERSION} | 2027科技风设计", 
                font=('Microsoft YaHei', 10), fg=self.text_secondary, bg=self.card_color).pack(pady=(4, 20))
        
        info_grid = tk.Frame(center_frame, bg=self.card_color)
        info_grid.pack(pady=10)
        
        infos = [
            ("程序名称", APP_NAME),
            ("版本号", APP_VERSION),
            ("作者", AUTHOR),
            ("微信号", WECHAT),
            ("联系电话", PHONE),
            ("支持平台", "Windows桌面端"),
        ]
        
        for i, (label, value) in enumerate(infos):
            row = i // 2
            col = i % 2
            
            item_frame = tk.Frame(info_grid, bg='#0a0e1a')
            item_frame.grid(row=row, column=col, padx=8, pady=6, sticky='nsew', ipadx=15, ipady=10)
            
            tk.Label(item_frame, text=label, font=('Microsoft YaHei', 9),
                    fg=self.text_secondary, bg='#0a0e1a').pack(anchor='w')
            tk.Label(item_frame, text=value, font=('Microsoft YaHei', 11, 'bold'),
                    fg=self.accent_color, bg='#0a0e1a').pack(anchor='w', pady=(2, 0))
        
        features_frame = tk.Frame(center_frame, bg=self.card_color)
        features_frame.pack(pady=20)
        
        tk.Label(features_frame, text="🌟 功能特点", font=('Microsoft YaHei', 12, 'bold'), 
                fg=self.text_color, bg=self.card_color).pack(anchor='w', pady=(0, 10))
        
        features = [
            "✅ 手动自由绘制霓虹边框",
            "✅ 矩形/椭圆框选工具",
            "✅ 6种预设霓虹颜色 + 自定义",
            "✅ 边框粗细 / 光晕强度 / 背景压暗调节",
            "✅ 5套精美预设模板",
            "✅ 历史记录管理",
            "✅ 三端自适应响应式设计",
        ]
        
        for feat in features:
            tk.Label(features_frame, text=feat, font=('Microsoft YaHei', 10),
                    fg=self.text_secondary, bg=self.card_color).pack(anchor='w', pady=2)
    
    def open_image(self):
        file_path = filedialog.askopenfilename(
            title="选择图片",
            filetypes=[("图片文件", "*.jpg *.jpeg *.png *.webp"), ("所有文件", "*.*")]
        )
        if not file_path:
            return
        
        try:
            self.original_image = Image.open(file_path).convert('RGBA')
            self.shapes = []
            self.background_darken = 0
            self.darken_var.set(0)
            self.darken_label.config(text="0%")
            
            self.update_canvas_display()
            self.show_info(f"图片加载成功：{os.path.basename(file_path)}")
        except Exception as e:
            messagebox.showerror("错误", f"图片加载失败：{str(e)}")
    
    def update_canvas_display(self):
        if not self.original_image:
            return
        
        self.canvas.update()
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        if canvas_width < 10 or canvas_height < 10:
            self.root.after(100, self.update_canvas_display)
            return
        
        img_width, img_height = self.original_image.size
        scale_w = (canvas_width - 40) / img_width
        scale_h = (canvas_height - 40) / img_height
        self.scale_factor = min(scale_w, scale_h, 1.0)
        
        display_width = int(img_width * self.scale_factor)
        display_height = int(img_height * self.scale_factor)
        
        self.display_image = self.original_image.copy()
        self.redraw_neon_effect()
        
        display_img = self.display_image.resize((display_width, display_height), Image.LANCZOS)
        self.photo_image = ImageTk.PhotoImage(display_img)
        
        self.canvas.delete("all")
        self.canvas.create_image(canvas_width // 2, canvas_height // 2, image=self.photo_image, anchor='center')
        
        self.canvas_offset_x = (canvas_width - display_width) // 2
        self.canvas_offset_y = (canvas_height - display_height) // 2
    
    def redraw_neon_effect(self):
        if not self.display_image:
            return
        
        self.display_image = self.original_image.copy()
        
        if self.background_darken > 0:
            darken = Image.new('RGBA', self.display_image.size, (0, 0, 0, int(255 * self.background_darken / 100)))
            self.display_image = Image.alpha_composite(self.display_image, darken)
        
        draw = ImageDraw.Draw(self.display_image)
        
        for shape in self.shapes:
            self.draw_shape_on_image(draw, shape)
    
    def draw_shape_on_image(self, draw, shape):
        color = shape['color']
        thickness = shape['thickness']
        glow = shape['glow']
        
        r, g, b = self.hex_to_rgb(color)
        
        if shape['type'] == 'freehand':
            if len(shape['points']) < 2:
                return
            
            if glow > 0:
                glow_layer = Image.new('RGBA', self.display_image.size, (0, 0, 0, 0))
                glow_draw = ImageDraw.Draw(glow_layer)
                
                for i in range(min(glow // 3, 10), 0, -1):
                    alpha = int(255 * (1 - i / (glow // 3 + 1)) / 3)
                    glow_color = (r, g, b, alpha)
                    glow_draw.line(shape['points'], fill=glow_color, width=thickness + i * 3, joint='curve')
                
                glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=glow // 4))
                self.display_image = Image.alpha_composite(self.display_image, glow_layer)
                draw = ImageDraw.Draw(self.display_image)
            
            draw.line(shape['points'], fill=color, width=thickness, joint='curve')
        
        elif shape['type'] == 'rect':
            x, y, w, h = shape['x'], shape['y'], shape['w'], shape['h']
            
            if glow > 0:
                for i in range(min(glow // 4, 8), 0, -1):
                    alpha = int(255 * (1 - i / (glow // 4 + 1)) / 3)
                    glow_color = (r, g, b, alpha)
                    draw.rectangle([x - i, y - i, x + w + i, y + h + i], outline=glow_color, width=thickness)
            
            draw.rectangle([x, y, x + w, y + h], outline=color, width=thickness)
        
        elif shape['type'] == 'ellipse':
            x, y, w, h = shape['x'], shape['y'], shape['w'], shape['h']
            
            if glow > 0:
                for i in range(min(glow // 4, 8), 0, -1):
                    alpha = int(255 * (1 - i / (glow // 4 + 1)) / 3)
                    glow_color = (r, g, b, alpha)
                    draw.ellipse([x - i, y - i, x + w + i, y + h + i], outline=glow_color, width=thickness)
            
            draw.ellipse([x, y, x + w, y + h], outline=color, width=thickness)
        
        elif shape['type'] == 'eraser':
            if len(shape['points']) < 2:
                return
            draw.line(shape['points'], fill=(0, 0, 0, 0), width=thickness * 3, joint='curve')
    
    def hex_to_rgb(self, hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    def start_drawing(self, event):
        if not self.original_image:
            return
        
        self.is_drawing = True
        
        img_x = (event.x - self.canvas_offset_x) / self.scale_factor
        img_y = (event.y - self.canvas_offset_y) / self.scale_factor
        
        img_x = max(0, min(img_x, self.original_image.width))
        img_y = max(0, min(img_y, self.original_image.height))
        
        self.last_x = img_x
        self.last_y = img_y
        self.start_x = img_x
        self.start_y = img_y
        
        if self.current_tool in ('freehand', 'eraser'):
            self.shapes.append({
                'type': self.current_tool,
                'color': self.neon_color,
                'thickness': self.neon_thickness * (3 if self.current_tool == 'eraser' else 1),
                'glow': 0 if self.current_tool == 'eraser' else self.glow_intensity,
                'points': [(img_x, img_y)]
            })
    
    def draw(self, event):
        if not self.is_drawing or not self.original_image:
            return
        
        img_x = (event.x - self.canvas_offset_x) / self.scale_factor
        img_y = (event.y - self.canvas_offset_y) / self.scale_factor
        
        img_x = max(0, min(img_x, self.original_image.width))
        img_y = max(0, min(img_y, self.original_image.height))
        
        if self.current_tool in ('freehand', 'eraser'):
            self.shapes[-1]['points'].append((img_x, img_y))
            self.redraw_neon_effect()
            self.update_canvas_display_only()
        
        elif self.current_tool in ('rect', 'ellipse'):
            self.temp_shape = {
                'type': self.current_tool,
                'color': self.neon_color,
                'thickness': self.neon_thickness,
                'glow': self.glow_intensity,
                'x': min(self.start_x, img_x),
                'y': min(self.start_y, img_y),
                'w': abs(img_x - self.start_x),
                'h': abs(img_y - self.start_y)
            }
            self.redraw_neon_effect()
            draw = ImageDraw.Draw(self.display_image)
            self.draw_shape_on_image(draw, self.temp_shape)
            self.update_canvas_display_only()
    
    def stop_drawing(self, event):
        if not self.is_drawing:
            return
        
        self.is_drawing = False
        
        if self.current_tool in ('rect', 'ellipse') and self.temp_shape:
            if self.temp_shape['w'] > 5 and self.temp_shape['h'] > 5:
                self.shapes.append(self.temp_shape)
            self.temp_shape = None
        
        self.redraw_neon_effect()
        self.update_canvas_display()
    
    def update_canvas_display_only(self):
        if not self.display_image:
            return
        
        display_width = int(self.display_image.width * self.scale_factor)
        display_height = int(self.display_image.height * self.scale_factor)
        
        display_img = self.display_image.resize((display_width, display_height), Image.LANCZOS)
        self.photo_image = ImageTk.PhotoImage(display_img)
        
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        self.canvas.delete("all")
        self.canvas.create_image(canvas_width // 2, canvas_height // 2, image=self.photo_image, anchor='center')
    
    def set_tool(self, tool):
        self.current_tool = tool
        for t, btn in self.tool_buttons.items():
            if t == tool:
                btn.configure(bg=self.primary_color, fg='white')
            else:
                btn.configure(bg=self.card_color, fg=self.text_secondary)
        
        if tool == 'eraser':
            self.canvas.config(cursor='circle')
        else:
            self.canvas.config(cursor='crosshair')
    
    def set_color(self, color):
        self.neon_color = color
        for c, btn in self.color_buttons.items():
            if c == color:
                btn.configure(bd=5, relief='solid')
            else:
                btn.configure(bd=3, relief='solid')
    
    def choose_custom_color(self):
        color = colorchooser.askcolor(title="选择霓虹颜色", initialcolor=self.neon_color)
        if color:
            self.set_color(color[1])
    
    def update_thickness(self, value):
        self.neon_thickness = int(float(value))
        self.thickness_label.config(text=f"{int(float(value))}px")
    
    def update_glow(self, value):
        self.glow_intensity = int(float(value))
        self.glow_label.config(text=str(int(float(value))))
    
    def update_darken(self, value):
        self.background_darken = int(float(value))
        self.darken_label.config(text=f"{int(float(value))}%")
        if self.original_image:
            self.redraw_neon_effect()
            self.update_canvas_display_only()
    
    def reset_canvas(self):
        if not self.original_image:
            return
        if not messagebox.askyesno("确认", "确定要重置画布吗？所有绘制将被清除。"):
            return
        self.shapes = []
        self.background_darken = 0
        self.darken_var.set(0)
        self.darken_label.config(text="0%")
        self.redraw_neon_effect()
        self.update_canvas_display()
        self.show_info("画布已重置")
    
    def undo_shape(self):
        if not self.shapes:
            return
        self.shapes.pop()
        self.redraw_neon_effect()
        self.update_canvas_display()
        self.show_info("已撤销")
    
    def save_image(self):
        if not self.original_image:
            messagebox.showwarning("提示", "请先打开一张图片")
            return
        
        default_name = f"neon_effect_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        file_path = filedialog.asksaveasfilename(
            title="保存图片",
            defaultextension=".png",
            initialfile=default_name,
            filetypes=[("PNG图片", "*.png"), ("JPEG图片", "*.jpg"), ("所有文件", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            output_img = self.display_image.convert('RGB')
            output_img.save(file_path)
            
            target = self.target_desc.get('1.0', tk.END).strip()
            
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO records (mode, original_image, output_image, target_description, 
                                     neon_color, neon_thickness, glow_intensity, background_darken, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', ('manual', '', file_path, target, self.neon_color, 
                  self.neon_thickness, self.glow_intensity, self.background_darken,
                  datetime.datetime.now().isoformat()))
            conn.commit()
            conn.close()
            
            self.refresh_history()
            messagebox.showinfo("成功", f"图片已保存到：\n{file_path}")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败：{str(e)}")
    
    def show_info(self, message):
        self.root.after(0, lambda: self._show_toast(message))
    
    def _show_toast(self, message):
        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        toast.attributes('-topmost', True)
        
        label = tk.Label(toast, text=message, font=('Microsoft YaHei', 10),
                        bg='#1e293b', fg='white', padx=20, pady=10,
                        bd=1, relief='solid')
        label.pack()
        
        x = self.root.winfo_x() + self.root.winfo_width() - 250
        y = self.root.winfo_y() + 80
        toast.geometry(f"+{x}+{y}")
        
        def fade_out():
            for i in range(10, 0, -1):
                toast.attributes('-alpha', i / 10)
                toast.update()
                toast.after(30)
            toast.destroy()
        
        toast.after(2000, fade_out)


def main():
    root = tk.Tk()
    
    try:
        root.iconbitmap(default='')
    except:
        pass
    
    app = NeonStudioApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
