FROM python:3.9-slim

# 设置pip镜像源
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app

COPY requirements.txt .

# 使用清华镜像源安装依赖
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

CMD ["python", "app.py"]