FROM python:3.11-slim

# 设置代理环境变量
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY}

# 配置 pip 使用清华镜像源
RUN pip config set global.index-url https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple \
    && pip config set global.trusted-host mirrors.tuna.tsinghua.edu.cn

# 配置 apt 使用代理（如果有）
RUN if [ -n "$HTTP_PROXY" ]; then \
        echo "Acquire::http::Proxy \"$HTTP_PROXY\";" > /etc/apt/apt.conf.d/proxy.conf; \
    fi \
    && if [ -n "$HTTPS_PROXY" ]; then \
        echo "Acquire::https::Proxy \"$HTTPS_PROXY\";" >> /etc/apt/apt.conf.d/proxy.conf; \
    fi

# 安装 curl 用于 FTPS 连接，并创建 tmp 目录
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /tmp && chmod 1777 /tmp

# 设置工作目录
WORKDIR /app

# 创建应用 tmp 目录
RUN mkdir -p /app/tmp

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY app.py .
COPY templates/ templates/
COPY static/ static/

# 暴露端口
EXPOSE 5000

# 运行应用
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
