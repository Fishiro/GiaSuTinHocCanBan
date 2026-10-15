# File: Dockerfile
FROM --platform=linux/amd64 python:3.11-slim

WORKDIR /app

# Chỉ cài đặt các thư viện gọn nhẹ phục vụ xử lý Excel và API để giữ ảnh Docker và RAM < 1GB
RUN pip install --no-cache-dir requests openpyxl pandas python-dotenv flask flask-cors flask-limiter flask-talisman

COPY . /app

ENTRYPOINT ["python", "main.py"]