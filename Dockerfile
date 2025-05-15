# 使用 Docker Hub 的官方 Python 镜像
FROM python:3.9-slim
# 设置容器中的工作目录
WORKDIR /app

# 安装 Poppler 和其他依赖项
# apt-get 更新并安装 poppler-utils
# 清理 apt 缓存以减小图像大小
RUN apt-get update && \
    apt-get install -y --no-install-recommends poppler-utils && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
# 设置 pip mirror（可选，但在某些地区对速度有好处）
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
# 将需求文件复制到容器中
COPY requirements.txt .
# 使用指定的镜像安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt
# 将应用程序代码的其余部分复制到容器中
COPY . .

# 为无缓冲的 Python 输出设置环境变量
ENV PYTHONUNBUFFERED=1

# 运行应用程序的命令
CMD ["python", "app.py"]
