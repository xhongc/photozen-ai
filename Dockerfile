FROM registry.cn-hangzhou.aliyuncs.com/xhongc/linux_arm64_python:3.9.12-slim-bullseye AS builder
USER root
# 镜像加速
COPY ./sources.list /etc/apt/sources.list
RUN apt update && \
    apt install -y libgl1-mesa-glx libglib2.0-0 libsm6 libxrender1 libfontconfig1 g++ && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/log/*

WORKDIR /app
COPY requirements.txt .

# 安装依赖包到临时目录
RUN pip3 install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple -t /app/deps

# 最终镜像
FROM registry.cn-hangzhou.aliyuncs.com/xhongc/linux_arm64_python:3.9.12-slim-bullseye
USER root
COPY ./sources.list /etc/apt/sources.list
RUN apt update && \
    apt install -y libgl1-mesa-glx libglib2.0-0 libsm6 libxrender1 libfontconfig1 && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/log/*

WORKDIR /app
COPY --from=builder /app/deps /usr/local/lib/python3.9/site-packages/
COPY . .

EXPOSE 8060

CMD [ "python3", "main.py" ]
