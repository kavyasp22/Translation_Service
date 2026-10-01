# Translation Service — Console

React UI for testing the translation service. Shows the translated text plus
the actual routing decision: which model served the request, whether a
fallback was triggered, detected script/language, and latency.

## Setup

```bash
cd frontend
npm install
cp .env.example .env   # point VITE_API_BASE_URL at your running backend
npm run dev
```

Opens on http://localhost:5173. Make sure the backend (`uvicorn app.main:app`)
is running and CORS-reachable — if you deploy the frontend on a different
origin than `localhost`, add a CORS middleware to `app/main.py` on the
backend allowing that origin.

## Build for production

```bash
npm run build
```

Outputs static files to `dist/` — serve with any static host (nginx, Vercel,
Netlify, etc.), pointed at your deployed backend via `VITE_API_BASE_URL`.
