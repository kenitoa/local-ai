FROM python:3.11-slim
WORKDIR /app
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-kor \
    libgl1 \
    libglib2.0-0 \
  && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir \
  fastapi==0.115.0 \
  uvicorn==0.30.6 \
  pillow==10.4.0 \
  pytesseract==0.3.13 \
  opencv-python-headless==4.10.0.84 \
  numpy==1.26.4 \
  transformers==4.44.2
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.4.1
COPY app.py /app/app.py
RUN mkdir -p /app/models /app/logs
ENV SERVICE_NAME=vision-server SERVICE_PORT=8002 OCR_ENGINE=auto OCR_LANGS=kor+eng
EXPOSE 8002
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8002/health', timeout=2).status==200 else 1)"
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8002"]
