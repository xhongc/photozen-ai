import gc
from dotenv import load_dotenv
import os
import sys
from fastapi import Depends, FastAPI, File, UploadFile, HTTPException, Header
from fastapi.responses import HTMLResponse
import numpy as np
import cv2
import asyncio
from pydantic import BaseModel
from PIL import Image
from io import BytesIO
from insightface.utils import storage
import uvicorn

from config import AppConfig

from starlette.templating import Jinja2Templates
from starlette.requests import Request
import clip as local_clip
import docker
from model_manager import ModelManager

load_dotenv()

app = FastAPI(
    title="PhotoZen API",
    version="1.0.0"
)
templates = Jinja2Templates(directory='templates')
# 初始化配置和模型管理器
config = AppConfig()
model_manager = ModelManager()
try:
    docker_name = 'photozen-ai'
    client = docker.DockerClient(base_url='unix://var/run/docker.sock')
except Exception as e:
    print(f"Docker 连接失败: {e}")
    client = None

storage.BASE_REPO_URL = config.BASE_REPO_URL

# 查询容器日志


def get_container_logs(container_id_or_name):
    if not client:
        return ''
    try:
        container = client.containers.get(container_id_or_name)
        # 只获取最近100行日志
        logs = container.logs(tail=100).decode('utf-8')
        return logs
    except docker.errors.NotFound:
        print(f"容器 {container_id_or_name} 未找到。")
    except Exception as e:
        print(f"查询日志时出错: {e}")
        return ''

def calculate_cpu_percent(stats):
    """
    根据 Docker stats API 返回的数据计算 CPU 使用率
    :param stats: Docker stats API 返回的容器统计数据
    :return: CPU 使用率百分比
    """
    cpu_count = stats["cpu_stats"]["online_cpus"]
    # 计算 CPU 使用时间差值
    cpu_delta = float(stats["cpu_stats"]["cpu_usage"]["total_usage"]) - \
        float(stats["precpu_stats"]["cpu_usage"]["total_usage"])

    # 计算系统 CPU 总时间差值
    system_delta = float(stats["cpu_stats"]["system_cpu_usage"]) - \
        float(stats["precpu_stats"]["system_cpu_usage"])

    # 计算 CPU 使用率
    if system_delta > 0.0:
        cpu_percent = (cpu_delta / system_delta) * cpu_count * 100.0
    return cpu_percent

# 查询容器 CPU 和内存占用
def get_container_stats(container_id_or_name):
    if not client:
        return 0, 0, 0
    try:
        container = client.containers.get(container_id_or_name)
        stats = container.stats(stream=False)
        cpu_percent = calculate_cpu_percent(stats)
        # 计算内存使用量(MB)
        memory_stats = stats['memory_stats']
        used_memory = memory_stats['usage'] - memory_stats.get('stats', {}).get('cache', 0)
        memory_usage = used_memory / 1024 / 1024
        
        # 计算内存使用率
        memory_limit = memory_stats['limit'] 
        memory_usage_percent = used_memory / memory_limit * 100
        return cpu_percent, memory_usage, memory_usage_percent
    except docker.errors.NotFound:
        print(f"容器 {container_id_or_name} 未找到。")
    except Exception as e:
        print(f"查询资源占用时出错: {e}")
    return 0, 0, 0


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index(request: Request):
    state = {
        "ocr_state": model_manager.rapid_ocr is not None,
        "clip_img_state": model_manager.clip_img_model is not None,
        "clip_txt_state": model_manager.clip_txt_model is not None,
        "face_state": model_manager.face_model is not None,
    }
    env_vars = {}
    with open('.env', 'r') as f:
        for line in f:
            key, value = line.strip().split('=')
            env_vars[key] = value
    docker_env_vars = {
        "API_KEY": config.api_auth_key,
        "HTTP_PORT": config.http_port,
        "MT_USE_DML": config.env_use_dml,
        "AUTO_LOAD_TXT_MODAL": config.env_auto_load_txt_modal,
        "DETECTOR_BACKEND": config.detector_backend,
        "RECOGNITION_MODEL": config.recognition_model,
        "DETECTION_THRESH": config.detection_thresh,
        "SERVER_RESTART_TIME": config.server_restart_time,
    }
    env_vars.update(docker_env_vars)
    # docker log
    docker_log = get_container_logs(docker_name)
    docker_log_list = docker_log.split('\n')
    docker_log = '\n'.join(docker_log_list[-200:])
    docker_log = docker_log.replace('`', '"').replace("\n", "<br>")
    cpu_percent, memory_usage, memory_usage_percent = get_container_stats(docker_name)
    return templates.TemplateResponse("index.html",
                                      {"request": request,
                                       "state": state,
                                       "env_vars": env_vars,
                                       "docker_log": docker_log,
                                       "cpu_percent": round(cpu_percent, 2),
                                       "memory_usage": round(memory_usage, 2),
                                       "memory_usage_percent": round(memory_usage_percent, 2)})


async def verify_header(api_key: str = Header(...)):
    if api_key != config.api_auth_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key


@app.post("/check")
async def check(api_key: str = Depends(verify_header)):
    return {
        'result': 'pass',
        "title": "PhotoZen AI",
    }


def restart_program():
    python = sys.executable
    os.execl(python, python, *sys.argv)


@app.post("/restart_v2", include_in_schema=False)
async def restart(api_key: str = Depends(verify_header)):
    restart_program()
    return {'result': 'pass'}


class EnvVars(BaseModel):
    API_AUTH_KEY: str = None
    HTTP_PORT: int = None
    MT_USE_DML: str = None
    AUTO_LOAD_TXT_MODAL: str = None
    DETECTOR_BACKEND: str = None
    RECOGNITION_MODEL: str = None
    DETECTION_THRESH: float = None
    SERVER_RESTART_TIME: int = None


@app.post("/save_env", include_in_schema=False)
async def save_env(env_vars: EnvVars, api_key: str = Depends(verify_header)):
    """
    保存环境变量并重启应用
    """
    try:
        # 更新环境变量写入.env文件
        with open('.env', 'w') as f:
            for key, value in env_vars.model_dump(exclude_none=True).items():
                f.write(f"{key}={value}\n")

        # 重启应用
        restart_program()
        return {'result': 'pass', 'message': '环境变量已保存，应用正在重启'}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存环境变量失败: {str(e)}")


def to_fixed(num):
    return str(round(num, 2))


def trans_result(result):
    texts = []
    scores = []
    boxes = []
    if result is None:
        return {'texts': texts, 'scores': scores, 'boxes': boxes}
    for res_i in result:
        dt_box = res_i[0]
        box = {
            'x': to_fixed(dt_box[0][0]),
            'y': to_fixed(dt_box[0][1]),
            'width': to_fixed(dt_box[1][0] - dt_box[0][0]),
            'height': to_fixed(dt_box[2][1] - dt_box[0][1])
        }
        boxes.append(box)
        texts.append(res_i[1])
        scores.append(f"{res_i[2]:.2f}")
    return {'texts': texts, 'scores': scores, 'boxes': boxes}


@app.post("/ocr")
async def ocr_image(file: UploadFile = File(...), api_key: str = Depends(verify_header)):
    """
    照片上文字识别
    """
    rapid_ocr = model_manager.load_ocr_model()
    image_bytes = await file.read()
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        height, width, _ = img.shape
        if width > 10000 or height > 10000:
            return {'result': [], 'msg': 'height or width out of range'}
        _result = rapid_ocr(img)
        result = trans_result(_result[0])
        del img
        del _result
        return {'result': result}
    except Exception as e:
        print(e)
        return {'result': [], 'msg': str(e)}


async def predict(predict_func, inputs, model):
    return await asyncio.get_running_loop().run_in_executor(None, predict_func, inputs, model)


@app.post("/clip/img")
async def clip_image(file: UploadFile = File(...), api_key: str = Depends(verify_header)):
    """
    照片语义识别
    """
    clip_img_model = model_manager.load_clip_img_model()
    image_bytes = await file.read()
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        result = await predict(local_clip.process_image, img, clip_img_model)
        return {'result': ["{:.16f}".format(vec) for vec in result]}
    except Exception as e:
        print(e)
        return {'result': [], 'msg': str(e)}


class ClipTxtRequest(BaseModel):
    text: str


@app.post("/clip/txt")
async def clip_txt(request: ClipTxtRequest, api_key: str = Depends(verify_header)):
    """
    文本语义识别
    """
    clip_txt_model = model_manager.load_clip_txt_model()
    text = request.text
    result = await predict(local_clip.process_txt, text, clip_txt_model)
    return {'result': ["{:.16f}".format(vec) for vec in result]}


def _represent(img, face_model):
    faces = face_model.get(img)
    results = []
    for face in faces:
        resp_obj = {}
        embedding = face.normed_embedding.astype(float)
        resp_obj["embedding"] = embedding.tolist()
        box = face.bbox
        resp_obj["facial_area"] = {"x": int(box[0]), "y": int(
            box[1]), "w": int(box[2] - box[0]), "h": int(box[3] - box[1])}
        resp_obj["face_confidence"] = face.det_score.astype(float)
        results.append(resp_obj)
    return results


@app.post("/represent")
async def face_represent(file: UploadFile = File(...), api_key: str = Depends(verify_header)):
    """
    人脸特征提取
    """
    face_model = model_manager.load_face_model()
    content_type = file.content_type
    image_bytes = await file.read()
    try:
        img = None
        if content_type == 'image/gif':
            # Use Pillow to read the first frame of the GIF file
            with Image.open(BytesIO(image_bytes)) as img:
                if img.is_animated:
                    img.seek(0)  # Seek to the first frame of the GIF
                frame = img.convert('RGB')  # Convert to RGB mode
                np_arr = np.array(frame)  # Convert to NumPy array
                # Convert RGB to BGR for OpenCV
                img = cv2.cvtColor(np_arr, cv2.COLOR_RGB2BGR)
        if img is None:
            # Use OpenCV for other image types
            np_arr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if img is None:
            err = f"The uploaded file {file.filename} is not a valid image format or is corrupted."
            print(err)
            return {'result': [], 'msg': str(err)}

        height, width, _ = img.shape
        if width > 10000 or height > 10000:
            return {'result': [], 'msg': 'height or width out of range'}

        data = {"detector_backend": config.detector_backend,
                "recognition_model": config.recognition_model}

        embedding_objs = await predict(_represent, img, face_model)
        del img
        data["result"] = embedding_objs
        for embedding_obj in embedding_objs:
            pass
        return data
    except Exception as e:
        if 'set enforce_detection' in str(e):
            return {'result': []}
        print(e)
        return {'result': [], 'msg': str(e)}


@app.post("/toggle_service/{service}", include_in_schema=False)
async def toggle_service(service: str, api_key: str = Depends(verify_header)):
    if service == 'ocr':
        if model_manager.rapid_ocr is None:
            model_manager.load_ocr_model()
        else:
            model_manager.rapid_ocr = None
            gc.collect()
    elif service == 'clip':
        if model_manager.clip_img_model is None:
            model_manager.load_clip_img_model()
        else:
            model_manager.clip_img_model = None
            gc.collect()
        if model_manager.clip_txt_model is None:
            model_manager.load_clip_txt_model()
        else:
            model_manager.clip_txt_model = None
            gc.collect()
    elif service == 'face':
        if model_manager.face_model is None:
            model_manager.load_face_model()
        else:
            model_manager.face_model = None
            gc.collect()
    return {'result': 'pass'}

@app.get("/logs", include_in_schema=False)
async def get_logs(api_key: str = Depends(verify_header)):
    # docker log
    docker_log = get_container_logs(docker_name)
    docker_log = docker_log.replace('`', '"')
    docker_log_list = docker_log.split('\n')
    return {'logs': docker_log_list[-200:]}

@app.get("/system_stats", include_in_schema=False)
async def get_system_stats(api_key: str = Depends(verify_header)):
    cpu_percent, memory_usage, memory_usage_percent = get_container_stats(docker_name)
    return {'cpu': round(cpu_percent, 2), 'memory': round(memory_usage, 2), 'memory_percent': round(memory_usage_percent, 2)}

if __name__ == "__main__":
    port = config.http_port
    uvicorn.run(app, host="0.0.0.0", port=port)
