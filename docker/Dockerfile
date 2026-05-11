FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cmake \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY pyproject.toml README.md ./
COPY core ./core
COPY adapters ./adapters
COPY scripts ./scripts

RUN pip install --no-cache-dir --no-deps -e .

ENTRYPOINT ["ai-code-optimize"]
CMD ["/projects/sample", "--target", "src/main.py", "--goal", "Improve performance while preserving behavior.", "--mode", "hybrid"]
