FROM python:3.11-slim
WORKDIR /app
# 추론 의존성 (자체 학습형 A안):
#   - transformers + peft : 콜드스타트 베이스 + 자체 LoRA 어댑터 로드
#   - accelerate          : device 배치
#   - torch (CPU wheel)   : 기본 안전 채널. GPU 환경에선 base image 를 cuda 로 바꾸거나
#                           PyTorch CUDA wheel 을 추가 설치한다.
#   - huggingface_hub     : 콜드스타트 베이스 디렉터리 메타 읽기 (다운로드는 backend 가 X,
#                           scripts/bootstrap_cold_start.py 가 호스트에서 수행)
RUN pip install --no-cache-dir fastapi==0.115.0 uvicorn==0.30.6 \
 && pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.4.0 \
 && pip install --no-cache-dir \
        transformers==4.44.2 \
        peft==0.12.0 \
        accelerate==0.34.2 \
        huggingface_hub==0.25.1 \
        safetensors==0.4.5
COPY app.py /app/app.py
COPY infer_engine.py /app/infer_engine.py
RUN mkdir -p /app/models /app/logs
ENV SERVICE_NAME=model-server SERVICE_PORT=8001 \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
EXPOSE 8001
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8001/health').status==200 else 1)"
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
