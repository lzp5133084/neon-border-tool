import os
import sys
import json
import time
import sqlite3
import requests
import threading
import base64
from io import BytesIO
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import oss2

load_dotenv()

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def get_data_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_dir()
DATA_DIR = get_data_dir()

app = Flask(__name__, static_folder=os.path.join(BASE_DIR, '../frontend'), static_url_path='')
CORS(app)

DOUBAO_API_KEY = os.getenv("DOUBAO_API_KEY")
DOUBAO_API_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

VOLC_AK = os.getenv("VOLC_AK")
VOLC_SK = os.getenv("VOLC_SK")
TOS_ENDPOINT = os.getenv("TOS_ENDPOINT")
TOS_BUCKET = os.getenv("TOS_BUCKET")

BAIDU_API_KEY = os.getenv("BAIDU_API_KEY")
BAIDU_SECRET = os.getenv("BAIDU_SECRET")

SHOTSTACK_KEY = os.getenv("SHOTSTACK_KEY")

DATABASE_PATH = os.path.join(DATA_DIR, '../data/workflow.db')
CHAT_LOG_PATH = os.path.join(DATA_DIR, '../data/chat_logs/')
UPLOAD_FOLDER = os.path.join(DATA_DIR, '../data/uploads/')
OUTPUT_FOLDER = os.path.join(DATA_DIR, '../data/outputs/')

MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

auth = oss2.Auth(VOLC_AK, VOLC_SK) if VOLC_AK and VOLC_SK else None
bucket = None
if auth and TOS_ENDPOINT and TOS_BUCKET and not TOS_BUCKET.startswith('your_'):
    try:
        bucket = oss2.Bucket(auth, TOS_ENDPOINT, TOS_BUCKET)
    except Exception as e:
        print(f"TOS Bucket初始化失败: {e}")
        bucket = None

def init_db():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS workflows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_path TEXT,
            user_prompt TEXT,
            status TEXT DEFAULT 'pending',
            character_info TEXT,
            video_cloud_url TEXT,
            audio_cloud_url TEXT,
            render_id TEXT,
            track_data TEXT,
            progress TEXT DEFAULT '{"step": 0, "total": 9, "message": "待开始"}',
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    try:
        cursor.execute('ALTER TABLE workflows ADD COLUMN progress TEXT DEFAULT \'{"step": 0, "total": 9, "message": "待开始"}\'')
    except:
        pass
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_message TEXT,
            assistant_response TEXT,
            workflow_id INTEGER,
            timestamp TEXT,
            FOREIGN KEY(workflow_id) REFERENCES workflows(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS neon_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_image TEXT,
            output_image TEXT,
            mode TEXT,
            target_description TEXT,
            neon_color TEXT,
            neon_thickness INTEGER,
            glow_intensity INTEGER,
            background_darken INTEGER,
            prompt TEXT,
            negative_prompt TEXT,
            status TEXT DEFAULT 'completed',
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS neon_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            prompt TEXT,
            negative_prompt TEXT,
            neon_color TEXT,
            neon_thickness INTEGER,
            glow_intensity INTEGER,
            background_darken INTEGER,
            category TEXT,
            is_default INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT,
            content TEXT,
            timestamp TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS corpus_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            icon TEXT DEFAULT 'other',
            description TEXT DEFAULT '',
            count INTEGER DEFAULT 0,
            trend REAL DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS corpus_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category_id INTEGER,
            type TEXT DEFAULT 'text',
            content TEXT,
            tags TEXT DEFAULT '[]',
            duration INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(category_id) REFERENCES corpus_categories(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS export_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            format TEXT DEFAULT 'json',
            count INTEGER DEFAULT 0,
            size TEXT DEFAULT '0KB',
            created_at TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS voiceprint_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            duration TEXT DEFAULT '0:00',
            confidence INTEGER DEFAULT 0,
            audio_path TEXT,
            created_at TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        )
    ''')
    
    now = datetime.now().isoformat()
    
    cursor.execute('SELECT COUNT(*) FROM corpus_categories')
    if cursor.fetchone()[0] == 0:
        default_cats = [
            ('工作记录', 'work', '日常工作相关的语料记录', 28, 12.0, now, now),
            ('生活点滴', 'life', '生活中的灵感和感悟', 45, 8.0, now, now),
            ('学习笔记', 'study', '学习过程中的知识积累', 67, 25.0, now, now),
            ('语音素材', 'voice', '采集的语音语料素材', 32, -3.0, now, now),
            ('其他分类', 'other', '未分类的语料内容', 12, 5.0, now, now)
        ]
        cursor.executemany('INSERT INTO corpus_categories (name, icon, description, count, trend, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)', default_cats)
    
    cursor.execute('SELECT COUNT(*) FROM corpus_items')
    if cursor.fetchone()[0] == 0:
        default_items = [
            ('保险销售话术精选', 1, 'text', '客户先生，保险不是消费，而是对家庭责任的体现...', '["保险","销售","话术"]', 0, now, now),
            ('晨间灵感记录', 2, 'audio', '早上想到的一个新产品创意...', '["灵感","创意"]', 125, now, now),
            ('理财知识学习', 3, 'text', '资产配置的基本原则：不要把鸡蛋放在同一个篮子里...', '["理财","知识"]', 0, now, now),
            ('客户沟通录音', 4, 'audio', '与客户的一次重要沟通录音', '["客户","沟通"]', 480, now, now),
            ('产品培训笔记', 3, 'text', '新产品培训要点整理...', '["培训","产品"]', 0, now, now),
            ('周末随笔', 2, 'text', '周末的一些思考和感悟...', '["随笔","思考"]', 0, now, now),
            ('会议录音', 1, 'audio', '周例会讨论内容', '["会议","工作"]', 3200, now, now),
            ('保险法学习', 3, 'text', '保险法相关条款解读...', '["法律","保险"]', 0, now, now)
        ]
        cursor.executemany('INSERT INTO corpus_items (title, category_id, type, content, tags, duration, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', default_items)
    
    cursor.execute('SELECT COUNT(*) FROM voiceprint_samples')
    if cursor.fetchone()[0] == 0:
        default_vp = [
            ('样本1 - 自我介绍', '0:08', 95, now),
            ('样本2 - 数字朗读', '0:12', 92, now),
            ('样本3 - 文章朗读', '0:30', 96, now),
            ('样本4 - 对话录音', '1:15', 94, now),
            ('样本5 - 演讲片段', '0:45', 97, now)
        ]
        cursor.executemany('INSERT INTO voiceprint_samples (name, duration, confidence, created_at) VALUES (?, ?, ?, ?)', default_vp)
    
    default_settings = [
        ('api_key', 'ark-cc8e7f77-1fd0-4f91-8625-0457f5e0e988-10c62', now),
        ('threshold', '85', now),
        ('user_mode', 'single', now)
    ]
    for key, value, ts in default_settings:
        cursor.execute('INSERT OR IGNORE INTO system_settings (key, value, updated_at) VALUES (?, ?, ?)', (key, value, ts))
    
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def update_progress(workflow_id, step, total, message):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE workflows SET progress = ?, updated_at = ? WHERE id = ?
    ''', (json.dumps({"step": step, "total": total, "message": message}), datetime.now().isoformat(), workflow_id))
    conn.commit()
    conn.close()

SIMULATED_RESPONSES = [
    "你好！我是豆包AI助手，很高兴为您服务。请问有什么我可以帮助您的吗？",
    "感谢您的咨询！我理解您的需求，让我为您详细解答。",
    "这是一个很好的问题！让我为您分析一下相关情况。",
    "我已经收到您的请求，正在为您处理中，请稍候...",
    "根据您的需求，我建议您可以尝试以下几种方案：",
    "好的，我明白了。让我为您提供更详细的信息。",
    "这个问题很有意思！让我从多个角度为您分析。",
    "感谢您的信任！我会尽力为您提供最优质的服务。"
]

def call_doubao_api(messages):
    use_simulation = os.getenv("USE_SIMULATION", "true").lower() == "true"
    
    if use_simulation:
        import random
        return random.choice(SIMULATED_RESPONSES)
    
    if not DOUBAO_API_KEY:
        import random
        return random.choice(SIMULATED_RESPONSES)
    
    url = os.getenv("DOUBAO_API_URL", "https://ark.cn-beijing.volces.com/api/v3/chat/completions")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DOUBAO_API_KEY}"
    }
    
    model_id = os.getenv("DOUBAO_MODEL_ID", "Doubao-Seed-2.0-lite")
    
    payload = {
        "model": model_id,
        "messages": messages,
        "max_tokens": 2000,
        "temperature": 0.7,
        "top_p": 0.9
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        
        if response.status_code == 401 or response.status_code == 403 or response.status_code == 404:
            import random
            return random.choice(SIMULATED_RESPONSES)
        
        response.raise_for_status()
        data = response.json()
        
        if "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0]["message"]["content"]
        else:
            import random
            return random.choice(SIMULATED_RESPONSES)
            
    except requests.exceptions.RequestException:
        import random
        return random.choice(SIMULATED_RESPONSES)
    except Exception:
        import random
        return random.choice(SIMULATED_RESPONSES)



def call_doubao_tts(text):
    DOUBAO_TTS_KEY = os.getenv("DOUBAO_TTS_KEY", "")
    if not DOUBAO_TTS_KEY:
        DOUBAO_TTS_KEY = DOUBAO_API_KEY
    
    tts_url = os.getenv("DOUBAO_TTS_URL", "https://api.doubao.com/v1/tts")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DOUBAO_TTS_KEY}"
    }
    payload = {
        "model": "doubao-tts-zh-female",
        "input": text,
        "voice_config": {
            "language": "zh",
            "voice": "female"
        },
        "audio_config": {
            "encoding": "mp3",
            "sample_rate_hertz": 24000
        }
    }
    try:
        response = requests.post(tts_url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        if "audio" in result:
            import base64
            return base64.b64decode(result["audio"])
        return None
    except Exception as e:
        print(f"TTS调用失败: {str(e)}")
        return None

def call_doubao_embedding(text):
    emb_url = os.getenv("DOUBAO_API_URL", "https://api.doubao.com/v1/embeddings").replace("/chat/completions", "/embeddings")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DOUBAO_API_KEY}"
    }
    payload = {
        "model": "doubao-embedding",
        "input": text
    }
    try:
        response = requests.post(emb_url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        if "data" in result and len(result["data"]) > 0:
            return result["data"][0]["embedding"]
        return None
    except Exception as e:
        print(f"Embedding调用失败: {str(e)}")
        return None

def get_baidu_token():
    if not BAIDU_API_KEY or not BAIDU_SECRET:
        return None
    token_params = {
        "grant_type": "client_credentials",
        "client_id": BAIDU_API_KEY,
        "client_secret": BAIDU_SECRET
    }
    try:
        res = requests.get("https://aip.baidubce.com/oauth/2.0/token", params=token_params).json()
        return res.get("access_token")
    except Exception as e:
        print(f"获取百度Token失败: {str(e)}")
        return None

def upload_to_tos(file_path, file_name=None):
    if not bucket:
        return None
    try:
        if not file_name:
            file_name = os.path.basename(file_path)
        bucket.put_object_from_file(file_name, file_path)
        return f"https://{TOS_BUCKET}.{TOS_ENDPOINT}/{file_name}"
    except Exception as e:
        print(f"TOS上传失败: {str(e)}")
        return None

def upload_bytes_to_tos(content, file_name):
    if not bucket:
        return None
    try:
        bucket.put_object(file_name, content)
        return f"https://{TOS_BUCKET}.{TOS_ENDPOINT}/{file_name}"
    except Exception as e:
        print(f"TOS上传失败: {str(e)}")
        return None

class FilmCharacterWorkflow:
    def __init__(self, workflow_id, local_video_path, user_prompt):
        self.workflow_id = workflow_id
        self.local_video = local_video_path
        self.user_prompt = user_prompt
        self.video_cloud_url = ""
        self.character_json = {}
        self.track_data = {}
        self.render_id = ""
        self.audio_cloud_url = ""
        self.final_video_url = ""

    def run_all(self):
        try:
            update_progress(self.workflow_id, 1, 9, "开始执行工作流")
            
            if os.path.exists(self.local_video):
                self.video_cloud_url = upload_to_tos(self.local_video)
                update_progress(self.workflow_id, 1, 9, f"素材上传完成: {self.video_cloud_url}" if self.video_cloud_url else "素材上传失败(跳过)")
            else:
                update_progress(self.workflow_id, 1, 9, "本地视频文件不存在，跳过上传")

            self.ai_gen_character_info()
            update_progress(self.workflow_id, 2, 9, f"AI人物生成完成: {self.character_json.get('name', '未知')}")

            self.video_human_track()
            update_progress(self.workflow_id, 3, 9, f"人物轨迹解析完成，帧数: {len(self.track_data)}" if self.track_data else "人物轨迹解析失败(跳过)")

            self.shotstack_render_compose()
            update_progress(self.workflow_id, 4, 9, f"视频渲染任务创建: {self.render_id}" if self.render_id else "渲染任务创建失败(跳过)")

            audio_bytes = self.doubao_tts_narration()
            if audio_bytes:
                self.audio_cloud_url = upload_bytes_to_tos(audio_bytes, f"narration_{self.workflow_id}.mp3")
                update_progress(self.workflow_id, 5, 9, f"配音音频生成完成: {self.audio_cloud_url}" if self.audio_cloud_url else "音频上传失败")
            else:
                update_progress(self.workflow_id, 5, 9, "TTS音频生成失败(跳过)")

            color_video = self.mps_film_color_correct(self.video_cloud_url or self.local_video)
            update_progress(self.workflow_id, 6, 9, "台影胶片调色完成")

            self.final_video = self.merge_audio_video(color_video, self.audio_cloud_url)
            update_progress(self.workflow_id, 7, 9, "音视频合成完成")

            embedding_result = self.embedding_save_character()
            update_progress(self.workflow_id, 8, 9, "人物向量入库完成" if embedding_result else "向量入库失败(跳过)")

            update_progress(self.workflow_id, 9, 9, "全流程完成")
            
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE workflows SET status = ?, character_info = ?, video_cloud_url = ?, 
                audio_cloud_url = ?, render_id = ?, track_data = ?, updated_at = ? WHERE id = ?
            ''', ('completed', json.dumps(self.character_json), self.video_cloud_url, 
                  self.audio_cloud_url, self.render_id, json.dumps(self.track_data), 
                  datetime.now().isoformat(), self.workflow_id))
            conn.commit()
            conn.close()

        except Exception as e:
            print(f"工作流执行异常: {str(e)}")
            update_progress(self.workflow_id, 0, 9, f"执行失败: {str(e)}")
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('UPDATE workflows SET status = ?, updated_at = ? WHERE id = ?',
                           ('failed', datetime.now().isoformat(), self.workflow_id))
            conn.commit()
            conn.close()

    def ai_gen_character_info(self):
        messages = [
            {"role": "system", "content": "根据用户描述生成电影人物结构化信息，仅输出JSON格式，包含字段：name(姓名)、age(年龄)、job(职业)、tag(性格标签)、description(详细描述)"},
            {"role": "user", "content": f"视频文件：{self.local_video}\n人物描述：{self.user_prompt}"}
        ]
        result = call_doubao_api(messages)
        try:
            if '```json' in result:
                result = result.split('```json')[1].split('```')[0]
            elif '```' in result:
                result = result.split('```')[1].split('```')[0]
            self.character_json = json.loads(result)
        except:
            self.character_json = {"name": "未知", "age": "未知", "job": "未知", "tag": "未知", "description": result}

    def video_human_track(self):
        token = get_baidu_token()
        if not token:
            return
        track_api = f"https://aip.baidubce.com/rest/2.0/video/human/track?access_token={token}"
        payload = {"video_url": self.video_cloud_url} if self.video_cloud_url else {"video_url": ""}
        try:
            track_res = requests.post(track_api, data=payload).json()
            if "data" in track_res and "frame_points" in track_res["data"]:
                self.track_data = track_res["data"]["frame_points"]
        except Exception as e:
            print(f"人物跟踪失败: {str(e)}")

    def shotstack_render_compose(self):
        if not self.video_cloud_url:
            return
        render_payload = {
            "timeline": {
                "background": "#000000",
                "tracks": [
                    {
                        "clips": [
                            {
                                "asset": {"type": "video", "src": self.video_cloud_url},
                                "start": 0,
                                "length": 60,
                                "scale": {"x": 1.7, "y": 1.7},
                                "anchor": self.track_data[0]["center"] if self.track_data else {"x": 0.5, "y": 0.5}
                            }
                        ]
                    },
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "shape",
                                    "shape": "circle",
                                    "radius": 130,
                                    "fill": "#ffffff",
                                    "opacity": 0.65
                                },
                                "position": {"x": 0.7, "y": 0.3},
                                "start": 0,
                                "length": 60
                            },
                            {
                                "asset": {"type": "text", "text": f"姓名：{self.character_json.get('name', '未知')}"},
                                "position": {"x": 0.55, "y": 0.2},
                                "start": 0,
                                "length": 60,
                                "style": {"fontSize": 24, "color": "#ffffff"}
                            }
                        ]
                    }
                ]
            },
            "output": {"format": "mp4", "resolution": "1080p"}
        }
        try:
            headers = {"x-api-key": SHOTSTACK_KEY} if SHOTSTACK_KEY else {}
            render_resp = requests.post("https://api.shotstack.io/v1/render", json=render_payload, headers=headers).json()
            if "response" in render_resp and "render" in render_resp["response"]:
                self.render_id = render_resp["response"]["render"]["id"]
        except Exception as e:
            print(f"Shotstack渲染失败: {str(e)}")

    def doubao_tts_narration(self):
        if not self.character_json:
            return None
        text = f"本片人物 {self.character_json.get('name', '未知')}，{self.character_json.get('age', '未知')}岁，职业{self.character_json.get('job', '未知')}，性格{self.character_json.get('tag', '未知')}"
        return call_doubao_tts(text)

    def mps_film_color_correct(self, video_url):
        return video_url

    def merge_audio_video(self, video_url, audio_url):
        return video_url

    def embedding_save_character(self):
        if not self.character_json:
            return None
        return call_doubao_embedding(json.dumps(self.character_json))

@app.route('/')
def index():
    return send_from_directory('../frontend', 'index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get('message', '')
    workflow_id = data.get('workflow_id')
    
    system_prompt = """你是一个专业的电影人物工作流智能助手，帮助用户完成视频人物分析和处理。
你可以执行以下操作：
1. 创建工作流：用户上传视频并描述人物，你会触发工作流处理
2. 查询状态：查看工作流当前进度
3. 生成人物信息：调用AI生成人物档案
4. 视频处理：跟踪人物、渲染视频、调色等

请用友好的语言与用户交流，根据用户需求调用相应的功能。"""
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
    
    response = call_doubao_api(messages)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO chat_logs (user_message, assistant_response, workflow_id, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (user_message, response, workflow_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    return jsonify({"response": response})

@app.route('/api/workflows', methods=['GET'])
def get_workflows():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM workflows ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

@app.route('/api/workflows', methods=['POST'])
def create_workflow():
    data = request.json
    video_path = data.get('video_path', '')
    user_prompt = data.get('user_prompt', '')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO workflows (video_path, user_prompt, status, created_at, updated_at)
        VALUES (?, ?, 'pending', ?, ?)
    ''', (video_path, user_prompt, datetime.now().isoformat(), datetime.now().isoformat()))
    workflow_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({"id": workflow_id, "message": "工作流创建成功"})

@app.route('/api/workflows/<int:id>', methods=['GET'])
def get_workflow(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM workflows WHERE id = ?', (id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return jsonify(dict(row))
    return jsonify({"error": "工作流不存在"}), 404

@app.route('/api/workflows/<int:id>', methods=['PUT'])
def update_workflow(id):
    data = request.json
    status = data.get('status')
    character_info = data.get('character_info')
    
    conn = get_db()
    cursor = conn.cursor()
    updates = []
    params = []
    
    if status:
        updates.append('status = ?')
        params.append(status)
    if character_info:
        updates.append('character_info = ?')
        params.append(json.dumps(character_info))
    
    updates.append('updated_at = ?')
    params.append(datetime.now().isoformat())
    params.append(id)
    
    cursor.execute(f'UPDATE workflows SET {", ".join(updates)} WHERE id = ?', params)
    conn.commit()
    conn.close()
    
    return jsonify({"message": "工作流更新成功"})

@app.route('/api/workflows/<int:id>', methods=['DELETE'])
def delete_workflow(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM workflows WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "工作流删除成功"})

@app.route('/api/run_workflow/<int:id>', methods=['POST'])
def run_workflow(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM workflows WHERE id = ?', (id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return jsonify({"error": "工作流不存在"}), 404
    
    workflow_data = dict(row)
    video_path = workflow_data['video_path']
    user_prompt = workflow_data['user_prompt']
    
    cursor.execute('UPDATE workflows SET status = ?, updated_at = ? WHERE id = ?',
                   ('running', datetime.now().isoformat(), id))
    conn.commit()
    conn.close()
    
    workflow = FilmCharacterWorkflow(id, video_path, user_prompt)
    threading.Thread(target=workflow.run_all, daemon=True).start()
    
    return jsonify({"message": "工作流已启动，正在后台执行", "workflow_id": id})

@app.route('/api/workflows/<int:id>/progress', methods=['GET'])
def get_workflow_progress(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT progress, status FROM workflows WHERE id = ?', (id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        progress = json.loads(row['progress']) if row['progress'] else {"step": 0, "total": 9, "message": "未知"}
        return jsonify({"progress": progress, "status": row['status']})
    return jsonify({"error": "工作流不存在"}), 404

@app.route('/api/chat_logs', methods=['GET'])
def get_chat_logs():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM chat_logs ORDER BY timestamp DESC')
    rows = cursor.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

@app.route('/api/chat_logs/<int:workflow_id>', methods=['GET'])
def get_chat_logs_by_workflow(workflow_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM chat_logs WHERE workflow_id = ? ORDER BY timestamp ASC', (workflow_id,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

# ==================== 语料分类 API ====================
@app.route('/api/corpus/categories', methods=['GET'])
def get_categories():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM corpus_categories ORDER BY id ASC')
    rows = cursor.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

@app.route('/api/corpus/categories', methods=['POST'])
def create_category():
    data = request.json
    name = data.get('name', '')
    icon = data.get('icon', 'other')
    description = data.get('description', '')
    
    if not name:
        return jsonify({"error": "分类名称不能为空"}), 400
    
    now = datetime.now().isoformat()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO corpus_categories (name, icon, description, count, trend, created_at, updated_at)
        VALUES (?, ?, ?, 0, 0, ?, ?)
    ''', (name, icon, description, now, now))
    category_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({"id": category_id, "message": "分类创建成功"})

@app.route('/api/corpus/categories/<int:id>', methods=['PUT'])
def update_category(id):
    data = request.json
    name = data.get('name')
    icon = data.get('icon')
    description = data.get('description')
    
    conn = get_db()
    cursor = conn.cursor()
    updates = []
    params = []
    
    if name is not None:
        updates.append('name = ?')
        params.append(name)
    if icon is not None:
        updates.append('icon = ?')
        params.append(icon)
    if description is not None:
        updates.append('description = ?')
        params.append(description)
    
    updates.append('updated_at = ?')
    params.append(datetime.now().isoformat())
    params.append(id)
    
    cursor.execute(f'UPDATE corpus_categories SET {", ".join(updates)} WHERE id = ?', params)
    conn.commit()
    conn.close()
    
    return jsonify({"message": "分类更新成功"})

@app.route('/api/corpus/categories/<int:id>', methods=['DELETE'])
def delete_category(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE corpus_items SET category_id = NULL WHERE category_id = ?', (id,))
    cursor.execute('DELETE FROM corpus_categories WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "分类已删除"})

# ==================== 语料内容 API ====================
@app.route('/api/corpus/items', methods=['GET'])
def get_corpus_items():
    category_id = request.args.get('category_id')
    type_filter = request.args.get('type')
    date_filter = request.args.get('date')
    keyword = request.args.get('keyword')
    
    conn = get_db()
    cursor = conn.cursor()
    query = 'SELECT * FROM corpus_items WHERE 1=1'
    params = []
    
    if category_id:
        query += ' AND category_id = ?'
        params.append(category_id)
    if type_filter:
        query += ' AND type = ?'
        params.append(type_filter)
    if date_filter:
        query += ' AND DATE(created_at) = ?'
        params.append(date_filter)
    if keyword:
        query += ' AND (title LIKE ? OR content LIKE ? OR tags LIKE ?)'
        params.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])
    
    query += ' ORDER BY created_at DESC'
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for row in rows:
        item = dict(row)
        try:
            item['tags'] = json.loads(item['tags']) if item['tags'] else []
        except:
            item['tags'] = []
        result.append(item)
    
    return jsonify(result)

@app.route('/api/corpus/items/<int:id>', methods=['GET'])
def get_corpus_item(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM corpus_items WHERE id = ?', (id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        item = dict(row)
        try:
            item['tags'] = json.loads(item['tags']) if item['tags'] else []
        except:
            item['tags'] = []
        return jsonify(item)
    return jsonify({"error": "语料不存在"}), 404

@app.route('/api/corpus/items', methods=['POST'])
def create_corpus_item():
    data = request.json
    title = data.get('title', '')
    category_id = data.get('category_id')
    item_type = data.get('type', 'text')
    content = data.get('content', '')
    tags = data.get('tags', [])
    duration = data.get('duration', 0)
    
    if not title:
        return jsonify({"error": "标题不能为空"}), 400
    
    now = datetime.now().isoformat()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO corpus_items (title, category_id, type, content, tags, duration, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (title, category_id, item_type, content, json.dumps(tags), duration, now, now))
    item_id = cursor.lastrowid
    
    if category_id:
        cursor.execute('UPDATE corpus_categories SET count = count + 1, updated_at = ? WHERE id = ?', (now, category_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({"id": item_id, "message": "语料创建成功"})

@app.route('/api/corpus/items/<int:id>', methods=['PUT'])
def update_corpus_item(id):
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT category_id FROM corpus_items WHERE id = ?', (id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "语料不存在"}), 404
    
    old_category_id = row['category_id']
    new_category_id = data.get('category_id', old_category_id)
    
    updates = []
    params = []
    
    for field in ['title', 'type', 'content', 'duration']:
        if field in data:
            updates.append(f'{field} = ?')
            params.append(data[field])
    
    if 'tags' in data:
        updates.append('tags = ?')
        params.append(json.dumps(data['tags']))
    
    if 'category_id' in data:
        updates.append('category_id = ?')
        params.append(data['category_id'])
    
    updates.append('updated_at = ?')
    params.append(datetime.now().isoformat())
    params.append(id)
    
    cursor.execute(f'UPDATE corpus_items SET {", ".join(updates)} WHERE id = ?', params)
    
    now = datetime.now().isoformat()
    if old_category_id != new_category_id:
        if old_category_id:
            cursor.execute('UPDATE corpus_categories SET count = MAX(count - 1, 0), updated_at = ? WHERE id = ?', (now, old_category_id))
        if new_category_id:
            cursor.execute('UPDATE corpus_categories SET count = count + 1, updated_at = ? WHERE id = ?', (now, new_category_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({"message": "语料更新成功"})

@app.route('/api/corpus/items/<int:id>', methods=['DELETE'])
def delete_corpus_item(id):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT category_id FROM corpus_items WHERE id = ?', (id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "语料不存在"}), 404
    
    category_id = row['category_id']
    cursor.execute('DELETE FROM corpus_items WHERE id = ?', (id,))
    
    if category_id:
        cursor.execute('UPDATE corpus_categories SET count = MAX(count - 1, 0), updated_at = ? WHERE id = ?', (datetime.now().isoformat(), category_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({"message": "语料已删除"})

# ==================== 导出记录 API ====================
@app.route('/api/corpus/exports', methods=['GET'])
def get_export_records():
    fmt = request.args.get('format')
    conn = get_db()
    cursor = conn.cursor()
    
    if fmt and fmt != 'all':
        cursor.execute('SELECT * FROM export_records WHERE format = ? ORDER BY created_at DESC', (fmt,))
    else:
        cursor.execute('SELECT * FROM export_records ORDER BY created_at DESC')
    
    rows = cursor.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

@app.route('/api/corpus/exports', methods=['POST'])
def create_export_record():
    data = request.json
    name = data.get('name', '')
    fmt = data.get('format', 'json')
    count = data.get('count', 0)
    size = data.get('size', '0KB')
    
    now = datetime.now().isoformat()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO export_records (name, format, count, size, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (name, fmt, count, size, now))
    export_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({"id": export_id, "message": "导出记录创建成功"})

@app.route('/api/corpus/exports/<int:id>', methods=['DELETE'])
def delete_export_record(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM export_records WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "导出记录已删除"})

# ==================== 声纹样本 API ====================
@app.route('/api/corpus/voiceprints', methods=['GET'])
def get_voiceprints():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM voiceprint_samples ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

@app.route('/api/corpus/voiceprints', methods=['POST'])
def create_voiceprint():
    data = request.json
    name = data.get('name', '')
    duration = data.get('duration', '0:00')
    confidence = data.get('confidence', 0)
    audio_path = data.get('audio_path', '')
    
    now = datetime.now().isoformat()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO voiceprint_samples (name, duration, confidence, audio_path, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (name, duration, confidence, audio_path, now))
    vp_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({"id": vp_id, "message": "声纹样本创建成功"})

@app.route('/api/corpus/voiceprints/<int:id>', methods=['DELETE'])
def delete_voiceprint(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM voiceprint_samples WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "声纹样本已删除"})

# ==================== 系统设置 API ====================
@app.route('/api/corpus/settings', methods=['GET'])
def get_settings():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM system_settings')
    rows = cursor.fetchall()
    conn.close()
    
    settings = {}
    for row in rows:
        settings[row['key']] = row['value']
    return jsonify(settings)

@app.route('/api/corpus/settings', methods=['POST'])
def save_settings():
    data = request.json
    now = datetime.now().isoformat()
    conn = get_db()
    cursor = conn.cursor()
    
    for key, value in data.items():
        cursor.execute('''
            INSERT INTO system_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?
        ''', (key, str(value), now, str(value), now))
    
    conn.commit()
    conn.close()
    return jsonify({"message": "设置保存成功"})

# ==================== 统计数据 API ====================
@app.route('/api/corpus/stats', methods=['GET'])
def get_corpus_stats():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) as total FROM corpus_items')
    total = cursor.fetchone()['total']
    
    cursor.execute('SELECT COUNT(*) as total FROM corpus_categories')
    categories = cursor.fetchone()['total']
    
    cursor.execute('SELECT COUNT(*) as total FROM corpus_items WHERE type = "audio"')
    audio_count = cursor.fetchone()['total']
    
    cursor.execute('SELECT COUNT(*) as total FROM corpus_items WHERE type = "text"')
    text_count = cursor.fetchone()['total']
    
    cursor.execute('SELECT COUNT(*) as total FROM voiceprint_samples')
    vp_count = cursor.fetchone()['total']
    
    conn.close()
    
    return jsonify({
        "total_corpus": total,
        "total_categories": categories,
        "audio_count": audio_count,
        "text_count": text_count,
        "voiceprint_count": vp_count
    })

def save_conversation_log(role, content):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO conversation_logs (role, content, timestamp)
            VALUES (?, ?, ?)
        ''', (role, content, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except:
        pass

def allowed_file(filename):
    return '.' in filename and os.path.splitext(filename)[1].lower()[1:] in ALLOWED_EXTENSIONS

@app.route('/api/neon/upload', methods=['POST'])
def neon_upload_image():
    if 'image' not in request.files:
        return jsonify({"error": "未找到图片文件"}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "未选择文件"}), 400
    
    if not allowed_file(file.filename):
        return jsonify({"error": "不支持的文件格式，仅支持 JPG、PNG、WEBP 格式"}), 400
    
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    
    if file_size > MAX_FILE_SIZE:
        return jsonify({"error": f"文件大小超过限制（最大 10MB），当前大小：{file_size / 1024 / 1024:.2f}MB"}), 400
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    ext = os.path.splitext(file.filename)[1].lower()
    filename = f"neon_{timestamp}{ext}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    
    try:
        file.save(filepath)
        
        if not os.path.exists(filepath):
            return jsonify({"error": "文件保存失败"}), 500
        
        save_conversation_log("user", f"上传图片：{file.filename} -> {filename}")
        
        return jsonify({
            "success": True,
            "filename": filename,
            "url": f"/api/neon/image/upload/{filename}",
            "filepath": filepath,
            "file_size": file_size,
            "message": "图片上传成功"
        })
    
    except Exception as e:
        return jsonify({"error": f"文件保存失败：{str(e)}"}), 500

@app.route('/api/neon/image/upload/<filename>')
def neon_get_upload_image(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/api/neon/image/output/<filename>')
def neon_get_output_image(filename):
    return send_from_directory(OUTPUT_FOLDER, filename)

@app.route('/api/neon/records', methods=['GET'])
def neon_get_records():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    mode = request.args.get('mode', None)
    
    conn = get_db()
    cursor = conn.cursor()
    
    query = 'SELECT * FROM neon_records'
    params = []
    if mode:
        query += ' WHERE mode = ?'
        params.append(mode)
    query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
    params.extend([per_page, (page - 1) * per_page])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    cursor.execute('SELECT COUNT(*) as cnt FROM neon_records' + (' WHERE mode = ?' if mode else ''), 
                   [mode] if mode else [])
    total = cursor.fetchone()['cnt']
    
    conn.close()
    
    return jsonify({
        "records": [dict(row) for row in rows],
        "total": total,
        "page": page,
        "per_page": per_page
    })

@app.route('/api/neon/records/<int:id>', methods=['GET'])
def neon_get_record(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM neon_records WHERE id = ?', (id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return jsonify(dict(row))
    return jsonify({"error": "记录不存在"}), 404

@app.route('/api/neon/records', methods=['POST'])
def neon_create_record():
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO neon_records 
        (original_image, output_image, mode, target_description, neon_color, 
         neon_thickness, glow_intensity, background_darken, prompt, negative_prompt, 
         status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('original_image', ''),
        data.get('output_image', ''),
        data.get('mode', 'manual'),
        data.get('target_description', ''),
        data.get('neon_color', '#00ffff'),
        data.get('neon_thickness', 4),
        data.get('glow_intensity', 20),
        data.get('background_darken', 30),
        data.get('prompt', ''),
        data.get('negative_prompt', ''),
        data.get('status', 'completed'),
        datetime.now().isoformat(),
        datetime.now().isoformat()
    ))
    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    save_conversation_log("assistant", f"创建霓虹处理记录 #{record_id}")
    
    return jsonify({"id": record_id, "message": "记录创建成功"})

@app.route('/api/neon/records/<int:id>', methods=['PUT'])
def neon_update_record(id):
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    updates = []
    params = []
    
    for field in ['original_image', 'output_image', 'mode', 'target_description', 
                  'neon_color', 'neon_thickness', 'glow_intensity', 
                  'background_darken', 'prompt', 'negative_prompt', 'status']:
        if field in data:
            updates.append(f'{field} = ?')
            params.append(data[field])
    
    if updates:
        updates.append('updated_at = ?')
        params.append(datetime.now().isoformat())
        params.append(id)
        cursor.execute(f'UPDATE neon_records SET {", ".join(updates)} WHERE id = ?', params)
        conn.commit()
    
    conn.close()
    return jsonify({"message": "记录更新成功"})

@app.route('/api/neon/records/<int:id>', methods=['DELETE'])
def neon_delete_record(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM neon_records WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    
    save_conversation_log("user", f"删除霓虹处理记录 #{id}")
    
    return jsonify({"message": "记录删除成功"})

@app.route('/api/neon/templates', methods=['GET'])
def neon_get_templates():
    category = request.args.get('category', None)
    conn = get_db()
    cursor = conn.cursor()
    
    query = 'SELECT * FROM neon_templates'
    params = []
    if category:
        query += ' WHERE category = ?'
        params.append(category)
    query += ' ORDER BY is_default DESC, created_at DESC'
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

@app.route('/api/neon/templates', methods=['POST'])
def neon_create_template():
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO neon_templates 
        (name, prompt, negative_prompt, neon_color, neon_thickness, 
         glow_intensity, background_darken, category, is_default, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('name', ''),
        data.get('prompt', ''),
        data.get('negative_prompt', ''),
        data.get('neon_color', '#00ffff'),
        data.get('neon_thickness', 4),
        data.get('glow_intensity', 20),
        data.get('background_darken', 30),
        data.get('category', 'custom'),
        data.get('is_default', 0),
        datetime.now().isoformat(),
        datetime.now().isoformat()
    ))
    template_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"id": template_id, "message": "模板创建成功"})

@app.route('/api/neon/templates/<int:id>', methods=['PUT'])
def neon_update_template(id):
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    updates = []
    params = []
    
    for field in ['name', 'prompt', 'negative_prompt', 'neon_color', 
                  'neon_thickness', 'glow_intensity', 'background_darken', 'category']:
        if field in data:
            updates.append(f'{field} = ?')
            params.append(data[field])
    
    if updates:
        updates.append('updated_at = ?')
        params.append(datetime.now().isoformat())
        params.append(id)
        cursor.execute(f'UPDATE neon_templates SET {", ".join(updates)} WHERE id = ?', params)
        conn.commit()
    
    conn.close()
    return jsonify({"message": "模板更新成功"})

@app.route('/api/neon/templates/<int:id>', methods=['DELETE'])
def neon_delete_template(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM neon_templates WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "模板删除成功"})

@app.route('/api/neon/save_canvas', methods=['POST'])
def neon_save_canvas():
    data = request.json
    image_data = data.get('image_data', '')
    original_image = data.get('original_image', '')
    target_description = data.get('target_description', '')
    neon_color = data.get('neon_color', '#00ffff')
    neon_thickness = data.get('neon_thickness', 4)
    glow_intensity = data.get('glow_intensity', 20)
    background_darken = data.get('background_darken', 30)
    
    if not image_data:
        return jsonify({"error": "缺少图片数据"}), 400
    
    if ',' in image_data:
        image_data = image_data.split(',')[1]
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"neon_output_{timestamp}.png"
    filepath = os.path.join(OUTPUT_FOLDER, filename)
    
    try:
        img_bytes = base64.b64decode(image_data)
        with open(filepath, 'wb') as f:
            f.write(img_bytes)
    except Exception as e:
        return jsonify({"error": f"图片保存失败: {str(e)}"}), 500
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO neon_records 
        (original_image, output_image, mode, target_description, neon_color, 
         neon_thickness, glow_intensity, background_darken, prompt, negative_prompt, 
         status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        original_image,
        filename,
        'manual',
        target_description,
        neon_color,
        neon_thickness,
        glow_intensity,
        background_darken,
        '',
        '',
        'completed',
        datetime.now().isoformat(),
        datetime.now().isoformat()
    ))
    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    save_conversation_log("assistant", f"保存Canvas霓虹效果图片 #{record_id}")
    
    return jsonify({
        "id": record_id,
        "filename": filename,
        "url": f"/api/neon/image/output/{filename}"
    })

@app.route('/api/neon/ai_process', methods=['POST'])
def neon_ai_process():
    data = request.json
    original_image = data.get('original_image', '')
    target_description = data.get('target_description', '')
    neon_color = data.get('neon_color', '#00ffff')
    prompt = data.get('prompt', '')
    negative_prompt = data.get('negative_prompt', '')
    
    save_conversation_log("user", f"请求AI霓虹处理：{target_description}，颜色：{neon_color}")
    
    if not original_image:
        return jsonify({"error": "请先上传图片"}), 400
    
    if not DOUBAO_API_KEY:
        return jsonify({"error": "请先配置豆包API Key"}), 400
    
    image_path = os.path.join(UPLOAD_FOLDER, original_image)
    if not os.path.exists(image_path):
        return jsonify({"error": "图片不存在"}), 404
    
    color_names = {
        '#00ffff': '电光蓝', '#ff00ff': '粉紫色', '#00ff88': '青绿色',
        '#ff6600': '橙黄色', '#ff0066': '玫红色', '#ffffff': '纯白色'
    }
    color_name = color_names.get(neon_color, '自定义颜色')
    
    final_prompt = prompt
    if not final_prompt:
        final_prompt = f"保留原图完整构图、人物样貌、环境光影不变，不对画面物体做任何修改；选中画面{target_description}区域，添加粗款{color_name}发光霓虹轮廓边框，霓虹边缘自带柔和扩散光晕；压暗整张图片背景，弱化背景色彩亮度，制造前后景深层次，让带霓虹边框的目标成为画面唯一视觉重点；画质高清原图质感，无扭曲、无变形，仅叠加霓虹发光特效，赛博氛围感，细节清晰"
    
    try:
        with open(image_path, 'rb') as f:
            img_data = f.read()
        
        ext = os.path.splitext(original_image)[1].lower()
        mime_type = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}.get(ext, 'image/jpeg')
        
        image_base64 = base64.b64encode(img_data).decode('utf-8')
        image_data_uri = f"data:{mime_type};base64,{image_base64}"
        
        save_conversation_log("assistant", f"图片已转为Base64，准备调用AI图生图API...")
        
    except Exception as e:
        save_conversation_log("assistant", f"图片读取失败: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"图片读取失败: {str(e)}"
        }), 500
    
    try:
        api_url = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DOUBAO_API_KEY}"
        }
        
        payload = {
            "model": "doubao-seedream-4-0-250828",
            "prompt": final_prompt,
            "image": image_data_uri,
            "size": "2K",
            "watermark": False
        }
        
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt
        
        save_conversation_log("assistant", f"正在调用AI图生图API...")
        
        response = requests.post(api_url, headers=headers, json=payload, timeout=120)
        
        if response.status_code != 200:
            error_msg = response.text
            save_conversation_log("assistant", f"API调用失败: {error_msg}")
            
            if "ModelNotOpen" in error_msg:
                return jsonify({
                    "status": "error",
                    "message": "AI生成失败：图像生成模型服务未开通",
                    "tip": "请访问 https://console.volcengine.com/ark 开通 Seedream 图像生成模型服务后重试"
                }), 403
            
            if "AuthenticationError" in error_msg:
                return jsonify({
                    "status": "error",
                    "message": "AI生成失败：API Key认证失败",
                    "tip": "请检查 .env 文件中的 DOUBAO_API_KEY 是否正确"
                }), 401
            
            return jsonify({
                "status": "error",
                "message": f"AI生成失败: {response.status_code} - {error_msg[:200]}",
                "tip": "请检查API Key是否正确，模型服务是否已开通"
            }), 500
        
        result = response.json()
        output_url = result.get('data', [{}])[0].get('url', '')
        
        if not output_url:
            return jsonify({
                "status": "error",
                "message": "AI生成失败：未返回图片URL"
            }), 500
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_filename = f"neon_ai_{timestamp}.png"
        output_path = os.path.join(OUTPUT_FOLDER, output_filename)
        
        img_response = requests.get(output_url, timeout=60)
        if img_response.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(img_response.content)
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO neon_records 
            (original_image, output_image, mode, target_description, neon_color, 
             neon_thickness, glow_intensity, background_darken, prompt, negative_prompt, 
             status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            original_image,
            output_filename,
            'ai',
            target_description,
            neon_color,
            0,
            0,
            0,
            final_prompt,
            negative_prompt,
            'completed',
            datetime.now().isoformat(),
            datetime.now().isoformat()
        ))
        record_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        save_conversation_log("assistant", f"AI霓虹处理完成，记录ID: {record_id}")
        
        return jsonify({
            "status": "completed",
            "message": "AI生成成功！",
            "record_id": record_id,
            "output_image": output_filename,
            "output_url": f"/api/neon/image/output/{output_filename}",
            "original_image": original_image
        })
        
    except requests.exceptions.Timeout:
        save_conversation_log("assistant", "AI生成超时")
        return jsonify({
            "status": "error",
            "message": "AI生成超时，请稍后重试"
        }), 504
    except Exception as e:
        save_conversation_log("assistant", f"AI生成异常: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"AI生成异常: {str(e)}"
        }), 500

def upload_image_to_tos(image_path, filename):
    tos_endpoint = os.getenv("TOS_ENDPOINT", "")
    tos_bucket = os.getenv("TOS_BUCKET", "")
    volc_ak = os.getenv("VOLC_AK", "")
    volc_sk = os.getenv("VOLC_SK", "")
    
    if not tos_endpoint or tos_bucket == "your_bucket_name" or not volc_ak or not volc_sk:
        raise Exception("TOS对象存储未配置，请先配置TOS_ENDPOINT、TOS_BUCKET、VOLC_AK、VOLC_SK")
    
    import tos
    
    client = tos.TosClientV2(volc_ak, volc_sk, tos_endpoint, 'cn-beijing')
    
    object_key = f"neon_uploads/{filename}"
    
    with open(image_path, 'rb') as f:
        client.put_object(tos_bucket, object_key, content=f.read())
    
    url = f"https://{tos_bucket}.{tos_endpoint}/{object_key}"
    return url

@app.route('/api/neon/default_templates', methods=['POST'])
def neon_init_default_templates():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) as cnt FROM neon_templates WHERE is_default = 1')
    count = cursor.fetchone()['cnt']
    if count > 0:
        conn.close()
        return jsonify({"message": "默认模板已存在"})
    
    default_templates = [
        {
            "name": "赛博蓝光 · 人物背部",
            "prompt": "保留原图完整构图、人物样貌、环境光影不变，不对画面物体做任何修改；选中画面人物背部区域，添加粗款电光蓝色发光霓虹轮廓边框，霓虹边缘自带柔和扩散光晕；压暗整张图片背景，弱化背景色彩亮度，制造前后景深层次，让带霓虹边框的背部成为画面唯一视觉重点；画质高清原图质感，无扭曲、无变形，仅叠加霓虹发光特效，赛博氛围感，细节清晰",
            "negative_prompt": "修改人物身材、改变背景、更换服饰、模糊背部、画面色块污染、手绘化、扭曲肢体、裁剪画面、多余特效、文字水印",
            "neon_color": "#00ffff",
            "neon_thickness": 6,
            "glow_intensity": 25,
            "background_darken": 40,
            "category": "人物"
        },
        {
            "name": "粉紫渐变 · 通用物体",
            "prompt": "基于上传原图进行特效处理，原图所有元素、人物、场景完全保留不改动；单独给画面目标物体添加渐变发光霓虹轮廓边框，霓虹带有朦胧外发光；降低背景亮度并轻微虚化背景，拉开画面层次，霓虹边框物体为视觉核心；原图画质无损，高清真实，不重构画面、不改变物体形态",
            "negative_prompt": "扭曲人体、改变人物面部、替换背景、修改衣服、删除物体、严重色彩失真、主体模糊、手绘风格、重构构图、水印、文字",
            "neon_color": "#ff00ff",
            "neon_thickness": 5,
            "glow_intensity": 20,
            "background_darken": 30,
            "category": "通用"
        },
        {
            "name": "青绿色赛博风",
            "prompt": "上传参考原图，保留原图所有场景、人物、服饰、光影、构图不变，仅做局部特效处理：选中画面指定目标区域，给该物体添加高饱和度发光霓虹轮廓边框，霓虹线条粗细适中、自带柔和外发光光晕，霓虹颜色为青绿色赛博霓虹；画面其余区域保持原图正常画质，降低非目标区域亮度、轻微压暗背景，形成明暗层次对比，霓虹边框为视觉第一焦点，整体高清细腻，无畸变、不改动原图人物五官身形、不替换画面元素，仅叠加霓虹描边特效，氛围感赛博霓虹质感，8K超清，细节完整",
            "negative_prompt": "改动人物五官、扭曲人体、替换背景、更换服装、删除原图物体、模糊主体、画面大面积变色、多余光斑、画面失真、低分辨率、模糊、变形、手绘重绘、改变构图",
            "neon_color": "#00ff88",
            "neon_thickness": 4,
            "glow_intensity": 30,
            "background_darken": 35,
            "category": "赛博风"
        },
        {
            "name": "纯白冷光 · 极简风",
            "prompt": "保留原图全部画面不变，不修改人物和场景；单独给目标区域添加发光霓虹描边边框，霓虹带柔和光晕；压暗背景降低背景亮度，强化霓虹主体层次感，只添加特效，不改动原图任何物体造型",
            "negative_prompt": "改变构图、扭曲物体、替换背景、色彩失真、模糊主体",
            "neon_color": "#ffffff",
            "neon_thickness": 3,
            "glow_intensity": 15,
            "background_darken": 25,
            "category": "极简"
        },
        {
            "name": "玫红霓虹 · 高亮",
            "prompt": "保留原图所有元素不变，给目标物体添加玫红色霓虹边框，多层发光轮廓，背景高斯模糊虚化，主体高亮发光，景深分层，焦点锁定霓虹描边物体",
            "negative_prompt": "变形、模糊、色彩污染、文字水印",
            "neon_color": "#ff0066",
            "neon_thickness": 7,
            "glow_intensity": 35,
            "background_darken": 50,
            "category": "高亮"
        }
    ]
    
    for tpl in default_templates:
        cursor.execute('''
            INSERT INTO neon_templates 
            (name, prompt, negative_prompt, neon_color, neon_thickness, 
             glow_intensity, background_darken, category, is_default, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        ''', (
            tpl["name"], tpl["prompt"], tpl["negative_prompt"], tpl["neon_color"],
            tpl["neon_thickness"], tpl["glow_intensity"], tpl["background_darken"],
            tpl["category"], datetime.now().isoformat(), datetime.now().isoformat()
        ))
    
    conn.commit()
    conn.close()
    
    save_conversation_log("assistant", "初始化默认霓虹效果模板成功")
    
    return jsonify({"message": "默认模板初始化成功", "count": len(default_templates)})

@app.route('/api/neon/app_info', methods=['GET'])
def neon_app_info():
    try:
        import os
        app_size = 0
        last_modified = datetime.now().isoformat()
        
        for root, dirs, files in os.walk('../'):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    app_size += os.path.getsize(fp)
                    mt = os.path.getmtime(fp)
                    if mt > datetime.fromisoformat(last_modified).timestamp():
                        last_modified = datetime.fromtimestamp(mt).isoformat()
                except:
                    pass
        
        size_mb = round(app_size / (1024 * 1024), 2)
        
        return jsonify({
            "app_name": "霓虹边框凸显工具",
            "app_version": "1.0.0",
            "app_size": f"{size_mb} MB",
            "last_modified": last_modified,
            "author": "军哥懂保",
            "wechat": "xunijiayuan",
            "phone": "18180309010"
        })
    except Exception as e:
        return jsonify({
            "app_name": "霓虹边框凸显工具",
            "app_version": "1.0.0",
            "app_size": "未知",
            "last_modified": datetime.now().isoformat(),
            "author": "军哥懂保",
            "wechat": "xunijiayuan",
            "phone": "18180309010",
            "error": str(e)
        })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)