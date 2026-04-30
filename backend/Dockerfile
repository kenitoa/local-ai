FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir \
    fastapi==0.115.0 \
    uvicorn==0.30.6 \
    pymysql==1.1.1 \
    python-multipart==0.0.9 \
    numpy==1.26.4
COPY app.py /app/app.py
COPY storage.py /app/storage.py
COPY db.py /app/db.py
RUN mkdir -p /app/data /app/logs
ENV SERVICE_NAME=backend SERVICE_PORT=8000 DATA_DIR=/app/data
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
