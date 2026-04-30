FROM python:3.11-slim
WORKDIR /app
# pciutils 는 lspci, kmod 는 lsmod 등 부수적 점검 명령에 도움이 됨(선택).
RUN apt-get update \
    && apt-get install -y --no-install-recommends pciutils \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir \
    fastapi==0.115.0 \
    uvicorn==0.30.6 \
    psutil==5.9.8 \
    requests==2.32.3
COPY app.py /app/app.py
RUN mkdir -p /app/logs /app/data
ENV SERVICE_NAME=hardware-detector \
    SERVICE_PORT=8005 \
    BACKEND_URL=http://backend:8000 \
    STORAGE_PATH=/app/data \
    PUSH_ON_STARTUP=1
EXPOSE 8005
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8005/health').status==200 else 1)"
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8005"]
