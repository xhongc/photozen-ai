from collections import deque
from datetime import datetime
import os

from rapidocr_onnxruntime import RapidOCR

from config import AppConfig
import clip as local_clip
from insightface.app import FaceAnalysis

# 单例模式：模型管理器类


class ModelManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ModelManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self.rapid_ocr = None
        self.clip_img_model = None
        self.clip_txt_model = None
        self.face_model = None
        self.restart_timer = None

        # 用于记录模型加载时间
        self.model_load_times = {
            'ocr': {'time': None, 'size': None},
            'clip': {'time': None, 'size': None},
            'face': {'time': None, 'size': None}
        }

        # 用于存储日志的队列
        self.log_queue = deque(maxlen=1000)

    def load_ocr_model(self):
        if self.rapid_ocr is None:
            print(f"{datetime.now()}-加载ocr模型")
            ocr_model_path = AppConfig().ocr_model_path
            params = {
                'det_model_path': os.path.join(ocr_model_path, 'ch_PP-OCRv4_det_infer.onnx'),
                'cls_model_path': os.path.join(ocr_model_path, 'ch_ppocr_mobile_v2.0_cls_infer.onnx'),
                'rec_model_path': os.path.join(ocr_model_path, 'ch_PP-OCRv4_rec_infer.onnx')
            }
            self.rapid_ocr = RapidOCR(**params)
        return self.rapid_ocr

    def load_clip_img_model(self):
        if self.clip_img_model is None:
            print(f"{datetime.now()}-加载clip img模型")
            self.clip_img_model = local_clip.load_img_model(
                use_dml=AppConfig().env_use_dml)
        return self.clip_img_model

    def load_clip_txt_model(self):
        if self.clip_txt_model is None:
            print(f"{datetime.now()}-加载clip txt模型")
            self.clip_txt_model = local_clip.load_txt_model(
                use_dml=AppConfig().env_use_dml)
        return self.clip_txt_model

    def load_face_model(self):
        if self.face_model is None:
            print(f"{datetime.now()}-加载face模型")
            providers = ["CPUExecutionProvider"]
            if AppConfig().env_use_dml:
                providers = ["DmlExecutionProvider", "CPUExecutionProvider"]
            faceAnalysis = FaceAnalysis(providers=providers, root=AppConfig().model_folder_path, allowed_modules=[
                                        'detection', 'recognition'], name=AppConfig().recognition_model)
            faceAnalysis.prepare(
                ctx_id=0, det_thresh=AppConfig().detection_thresh, det_size=(640, 640))
            self.face_model = faceAnalysis
        return self.face_model

    def set_restart_timer(self, timer):
        if self.restart_timer:
            self.restart_timer.cancel()
        self.restart_timer = timer
