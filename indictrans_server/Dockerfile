FROM pytorch/pytorch:2.13.0-cuda13.0-cudnn9-runtime

# git needed for IndicTransToolkit install from GitHub
RUN apt-get update && apt-get install -y --no-install-recommends \
    git build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

# torch is pre-installed in the base image — install only remaining deps
# This avoids re-downloading the ~2GB torch wheel on every build
COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages \
    "fastapi==0.115.0" \
    "uvicorn[standard]==0.30.6" \
    "transformers==4.44.2" \
    "sentencepiece==0.2.0" \
    "IndicTransToolkit @ git+https://github.com/VarunGumma/IndicTransToolkit.git"

COPY app.py .

ENV PYTHONUNBUFFERED=1
# Offline mode — never calls HuggingFace at runtime after weights are cached
ENV TRANSFORMERS_OFFLINE=1
ENV HF_DATASETS_OFFLINE=1
ENV HF_HUB_OFFLINE=1
# Safe GPU memory allocation — won't pre-allocate all VRAM on start
ENV PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

EXPOSE 8200
CMD ["python", "app.py"]
