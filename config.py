from dotenv import load_dotenv
import os
import sys
# 单例模式：应用配置类
class AppConfig:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AppConfig, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        load_dotenv()
        
        self.base_path = os.path.dirname(os.path.abspath(__file__))
        # 系统配置
        self.on_linux = sys.platform.startswith('linux')
        self.on_win = sys.platform.startswith('win')
        
        # API配置
        self.api_auth_key = os.getenv("API_KEY", "photozen")
        self.http_port = int(os.getenv("HTTP_PORT", "8060"))
        self.server_restart_time = int(os.getenv("SERVER_RESTART_TIME", "300"))
        
        # 模型配置
        self.env_use_dml = False
        self.env_auto_load_txt_modal = os.getenv("AUTO_LOAD_TXT_MODAL", "off") == "on"
        self.detector_backend = os.getenv("DETECTOR_BACKEND", "insightface")
        self.recognition_model = os.getenv("RECOGNITION_MODEL", "buffalo_l")
        self.detection_thresh = float(os.getenv("DETECTION_THRESH", "0.65"))
        
        # 模型路径配置
        self.ocr_model_path = os.path.join(self.base_path, "data", "ocr_model")
        self.BASE_REPO_URL = 'https://github.com/kqstone/mt-photos-insightface-unofficial/releases/download/models'
        self.model_folder_path = '~/.insightface'
        
    
    

