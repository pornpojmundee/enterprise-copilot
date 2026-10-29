# Nawa Copilot — API + web UI in one image (week 7).
#   docker build -t nawa-copilot .
#   docker compose --profile app up        # app + database on http://localhost:8000
#
# The bge-m3 embedding model is baked in (~2.3 GB) so a cold start does not download it.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf TOKENIZERS_PARALLELISM=false

WORKDIR /app

# CPU-only PyTorch (the default wheel bundles CUDA and is ~4x larger)
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN grep -v '^-e' requirements.txt > /tmp/req.txt && pip install -r /tmp/req.txt

ARG EMBEDDING_MODEL=BAAI/bge-m3
RUN python -c "from sentence_transformers import SentenceTransformer as S; S('${EMBEDDING_MODEL}')"

COPY pyproject.toml README.md ./
COPY src ./src
COPY scripts ./scripts
COPY db ./db
COPY data/documents ./data/documents
COPY data/seed ./data/seed
RUN pip install --no-deps -e . \
 && useradd --create-home --uid 10001 app && mkdir -p logs && chown -R app /app /opt/hf
USER app

ENV EMBEDDING_MODEL=${EMBEDDING_MODEL} DEMO_MODE=1 WARM_UP=1 SEED_ON_START=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"
CMD ["sh", "-c", "python scripts/bootstrap.py && exec uvicorn copilot.api.app:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
