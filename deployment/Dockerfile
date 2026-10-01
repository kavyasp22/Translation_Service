FROM python:3.11-slim

# Node.js is required for the googletrans subprocess backend
RUN apt-get update && apt-get install -y curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY node_backend/package.json node_backend/
RUN cd node_backend && npm install --omit=dev

COPY app app
COPY configs configs
COPY node_backend node_backend

ENV PYTHONUNBUFFERED=1
EXPOSE 8048

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8048"]
