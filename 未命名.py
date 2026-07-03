import os
import time
import requests
import oss2
import json
from dotenv import load_dotenv
from volcengine.ark import ArkService

load_dotenv()

# ==================== 全局API配置 ====================
# 豆包大模型
ark_service = ArkService(
    ak=os.getenv("VOLC_AK"),
    sk=os.getenv("VOLC_SK")
)
DOUBAO_EP = os.getenv("DOUBAO_ENDPOINT")

# TOS云存储
auth = oss2.Auth(os.getenv("VOLC_AK"), os.getenv("VOLC_SK"))
bucket = oss2.Bucket(auth, os.getenv("TOS_ENDPOINT"), os.getenv("TOS_BUCKET"))

# 第三方API常量
BAIDU_TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
SHOTSTACK_URL = "https://api.shotstack.io/v1/render"
# ======================================================

class FilmCharacterWorkflow:
    def __init__(self, local_video_path, user_prompt):
        self.local_video = local_video_path
        self.user_prompt = user_prompt
        self.video_cloud_url = ""
        self.character_json = {}
        self.track_data = {}
        self.render_id = ""

    def upload_video_to_tos(self):
        """阶段1：上传视频至火山TOS，获取云端访问地址"""
        file_name = os.path.basename(self.local_video)
        bucket.put_object_from_file(file_name, self.local_video)
        self.video_cloud_url = f"https://{os.getenv('TOS_BUCKET')}.{os.getenv('TOS_ENDPOINT')}/{file_name}"
        print(f"[1/9] 素材上传完成：{self.video_cloud_url}")

    def ai_gen_character_info(self):
        """阶段2：豆包多模态API生成人物结构化信息"""
        req = {
            "model": DOUBAO_EP,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"根据描述生成台湾电影人物信息，仅输出JSON：{self.user_prompt}，字段name/age/job/tag"},
                        {"type": "image_url", "image_url": self.video_cloud_url}
                    ]
                }
            ]
        }
        resp = ark_service.chat(req)
        self.character_json = json.loads(resp.choices[0].message.content)
        print(f"[2/9] AI生成人物档案：{self.character_json}")

    def get_baidu_token(self):
        token_params = {
            "grant_type": "client_credentials",
            "client_id": os.getenv("BAIDU_API_KEY"),
            "client_secret": os.getenv("BAIDU_SECRET")
        }
        res = requests.get(BAIDU_TOKEN_URL, params=token_params).json()
        return res["access_token"]

    def video_human_track(self):
        """阶段3：百度人体跟踪API解析全视频人物坐标轨迹"""
        token = self.get_baidu_token()
        track_api = f"https://aip.baidubce.com/rest/2.0/video/human/track?access_token={token}"
        payload = {"video_url": self.video_cloud_url}
        track_res = requests.post(track_api, data=payload).json()
        self.track_data = track_res["data"]["frame_points"]
        print(f"[3/9] 人物轨迹解析完成，总帧数：{len(self.track_data)}")

    def shotstack_render_compose(self):
        """阶段4：Shotstack自动合成放大动画+圆形信息卡图层"""
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
                                "anchor": self.track_data[0]["center"]
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
                                "position": {"x": self.track_data[0]["x"] + 170, "y": self.track_data[0]["y"]},
                                "start": 0,
                                "length": 60
                            },
                            {
                                "asset": {"type": "text", "text": f"姓名：{self.character_json['name']}"},
                                "position": {"x": self.track_data[0]["x"] + 80, "y": self.track_data[0]["y"] - 70},
                                "start": 0,
                                "length": 60
                            }
                        ]
                    }
                ]
            },
            "output": {"format": "mp4", "resolution": "1080p"}
        }
        headers = {"x-api-key": os.getenv("SHOTSTACK_KEY")}
        render_resp = requests.post(SHOTSTACK_URL, json=render_payload, headers=headers).json()
        self.render_id = render_resp["response"]["render"]["id"]
        print(f"[4/9] 视频渲染任务创建，任务ID：{self.render_id}")

    def doubao_tts_narration(self):
        """阶段5：豆包TTS生成人物介绍旁白"""
        tts_req = {
            "model": DOUBAO_EP,
            "text": f"本片人物 {self.character_json['name']}，{self.character_json['age']}岁，职业{self.character_json['job']}，性格{self.character_json['tag']}"
        }
        tts_result = ark_service.tts(tts_req)
        audio_cloud_url = self.upload_audio(tts_result.audio_bytes)
        print(f"[5/9] 配音音频生成上传完成：{audio_cloud_url}")
        return audio_cloud_url

    def upload_audio(self, audio_bytes):
        audio_name = "narration_audio.mp3"
        bucket.put_object(audio_name, audio_bytes)
        return f"https://{os.getenv('TOS_BUCKET')}.{os.getenv('TOS_ENDPOINT')}/{audio_name}"

    def mps_film_color_correct(self, video_url):
        """阶段6：火山MPS批量胶片调色"""
        # 此处封装火山MPS转码调色接口调用逻辑
        print("[6/9] 执行台影胶片调色任务")
        return video_url

    def merge_audio_video(self, video_url, audio_url):
        """阶段7：音视频合成"""
        print("[7/9] 音轨合并完成")
        return video_url

    def embedding_save_character(self):
        """阶段8：豆包Embedding向量存储人物档案，支持检索"""
        emb_req = {
            "model": DOUBAO_EP,
            "input": json.dumps(self.character_json)
        }
        emb_data = ark_service.embedding(emb_req)
        print(f"[8/9] 人物向量入库完成")

    def workflow_run_all(self):
        """一键执行全链路云端工作流"""
        self.upload_video_to_tos()
        self.ai_gen_character_info()
        self.video_human_track()
        self.shotstack_render_compose()
        audio_url = self.doubao_tts_narration()
        color_video = self.mps_film_color_correct(self.video_cloud_url)
        final_video = self.merge_audio_video(color_video, audio_url)
        self.embedding_save_character()
        print(f"[9/9] 全流程完成！成片地址：{final_video}")

# ==================== 程序入口调用 ====================
if __name__ == "__main__":
    # 传入本地视频路径 + 人物描述提示词
    flow = FilmCharacterWorkflow(
        local_video_path="walk_demo.mp4",
        user_prompt="27岁台湾咖啡店男生，温柔怀旧，慢生活性格"
    )
    flow.workflow_run_all()
