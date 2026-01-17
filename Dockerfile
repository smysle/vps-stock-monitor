FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 创建非特权用户
RUN groupadd -r appuser && useradd -r -g appuser appuser

# 复制代码
COPY . .

# 设置权限
RUN chown -R appuser:appuser /app

# 创建数据目录
RUN mkdir -p /app/data /app/logs && chown -R appuser:appuser /app/data /app/logs

# 切换到非特权用户
USER appuser

# 健康检查
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=5)" || exit 0

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["python", "main.py", "--api"]
