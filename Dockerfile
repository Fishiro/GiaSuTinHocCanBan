# File: Dockerfile
FROM --platform=linux/amd64 python:3.11-slim

WORKDIR /app

# Chỉ cài đặt các gói cần thiết cho Pipeline Excel QA & Web Backend để tối ưu RAM (< 1GB)
RUN pip install --no-cache-dir \
    requests \
    openpyxl \
    pandas \
    python-dotenv \
    flask \
    flask-cors \
    flask-limiter \
    flask-talisman \
    werkzeug

COPY . /app

ENTRYPOINT ["python", "main.py"]