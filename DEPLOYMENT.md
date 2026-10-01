# Deploying the Translation Service to your server

This assumes the server you showed the `docker inspect` output for — i.e. it
already has Docker, an NVIDIA GPU, and a vLLM Gemma server running. Steps
below get everything else running alongside it.

---

## 0. Prerequisites on the server

```bash
# Check these exist already
docker --version
nvidia-smi                 # confirms GPU + driver visible to Docker
python3 --version           # need 3.11+
redis-cli --version 2>/dev/null || echo "redis not installed yet"
```

If Redis isn't installed:
```bash
sudo apt-get update && sudo apt-get install -y redis-server
sudo systemctl enable --now redis-server
```

---

## 1. Get the code onto the server

If you're pushing to GitHub first (recommended, so you can pull updates later):
```bash
# on your local machine, from the translation_service folder
git init
git add .
git commit -m "Initial translation service"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main

# on the server
git clone <your-repo-url>
cd translation_service
```

Or just `scp`/upload the folder directly if you're skipping GitHub for now.

---

## 2. Start your model servers

### Gemma (you already have this running per your setup)
Confirm it's up:
```bash
curl http://localhost:11456/v1/models
```

### Qwen — currently `exited` per your docker inspect, start it:
```bash
docker start vllm_qwen3_vl_8b
docker ps | grep qwen          # confirm it's Running and note the published port
```
Whatever port shows up in `docker ps` (format `0.0.0.0:XXXX->8000/tcp`), that's
your `TRANSLATE_QWEN_BASE_URL` — e.g. if it's `8001`, that's
`http://localhost:8001/v1`.

### IndicTrans2 — needs to be started separately (own venv, own GPU slice)
```bash
cd indictrans_server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# first run downloads ~2-4GB of weights - make sure this box has internet
# access to huggingface.co
nohup python app.py > indictrans.log 2>&1 &
deactivate
cd ..
curl http://localhost:8100/health   # should return {"status": "ok"}
```

Keep this running long-term via `systemd` rather than `nohup` for production
— see step 5.

---

## 3. Configure the backend

```bash
cp .env.example .env 2>/dev/null || true   # if you add one; otherwise create .env directly
```

Create `.env` in the project root:
```bash
TRANSLATE_GEMMA_BASE_URL=http://localhost:11456/v1
TRANSLATE_QWEN_BASE_URL=http://localhost:<qwen-port>/v1
TRANSLATE_INDICTRANS_SERVICE_URL=http://localhost:8100
TRANSLATE_REDIS_URL=redis://localhost:6379/0
TRANSLATE_CORS_ALLOWED_ORIGINS=["https://your-frontend-domain.com"]
```

---

## 4. Install and run the backend

The `googletrans` backend calls a Node.js subprocess (`node_backend/`), so
Node.js is required here too, not just Python:
```bash
node --version || echo "install Node.js 18+ first"
cd node_backend && npm install && cd ..
```

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Quick manual check first
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open a second terminal and test:
```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/translate \
  -H "Content-Type: application/json" \
  -d '{"text": "नमस्ते, आप कैसे हैं?", "source_lang": "auto", "target_lang": "en"}'
```

If both work, `Ctrl+C` the manual run and set it up to run persistently (step 5).

---

## 5. Run it persistently with systemd (recommended over nohup)

`/etc/systemd/system/translation-api.service`:
```ini
[Unit]
Description=Translation Service API
After=network.target redis-server.service

[Service]
Type=simple
User=<your-user>
WorkingDirectory=/path/to/translation_service
EnvironmentFile=/path/to/translation_service/.env
ExecStart=/path/to/translation_service/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/indictrans2.service`:
```ini
[Unit]
Description=IndicTrans2 Microservice
After=network.target

[Service]
Type=simple
User=<your-user>
WorkingDirectory=/path/to/translation_service/indictrans_server
ExecStart=/path/to/translation_service/indictrans_server/venv/bin/python app.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable both:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now translation-api
sudo systemctl enable --now indictrans2
sudo systemctl status translation-api
```

Logs: `journalctl -u translation-api -f`

---

## 6. Build and serve the frontend

```bash
cd frontend
npm install
echo "VITE_API_BASE_URL=https://your-api-domain.com" > .env
npm run build
```

This produces `frontend/dist/` — static files. Serve them with nginx:

`/etc/nginx/sites-available/translation-frontend`:
```nginx
server {
    listen 80;
    server_name your-frontend-domain.com;
    root /path/to/translation_service/frontend/dist;
    index index.html;
    location / {
        try_files $uri /index.html;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/translation-frontend /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Add HTTPS with `certbot --nginx` if this is public-facing.

---

## 7. Reverse-proxy the API too (recommended over exposing :8000 directly)

`/etc/nginx/sites-available/translation-api`:
```nginx
server {
    listen 80;
    server_name your-api-domain.com;
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Then update `frontend/.env`'s `VITE_API_BASE_URL` to `https://your-api-domain.com`
and rebuild (`npm run build`).

---

## 8. Final checklist

```bash
sudo systemctl status redis-server translation-api indictrans2
docker ps | grep -E "gemma|qwen"          # both Running
curl https://your-api-domain.com/health   # all models report true (or at least gemma)
```

Open `https://your-frontend-domain.com` and run a real translation through
the UI — check the routing panel shows the model you expect for that language.

## Common gotchas

- **CORS errors in the browser console** → `TRANSLATE_CORS_ALLOWED_ORIGINS` in
  `.env` doesn't match your actual frontend URL exactly (including https vs http).
- **`/translate` times out** → check `curl` each model backend directly
  (`:11456/v1/models`, `:<qwen-port>/v1/models`, `:8100/health`) to isolate
  which one is actually down before assuming the whole pipeline is broken.
- **IndicTrans2 OOMs on the GPU** → it's sharing the GPU with Gemma/Qwen;
  check `nvidia-smi` for free memory, or run IndicTrans2 on CPU
  (`DEVICE` falls back automatically if no GPU is visible to that process)
  if memory is tight.
