# Sentiment-Analyzer

Paste a Flipkart product link and get a review breakdown: overall verdict, what people say about each aspect, and how trustworthy the reviews look. Every claim links back to the reviews behind it.

- **Backend:** Python 3.11+, FastAPI, httpx (`/backend`)
- **Frontend:** Next.js, TypeScript, Tailwind (`/frontend`)

## How reviews are collected

No browser is needed. The backend fetches Flipkart review pages with plain HTTP (`httpx`) and reads the reviews from the JSON Flipkart embeds in each page (`window.__INITIAL_STATE__`). If a page has no such JSON, it falls back to parsing the HTML review cards. Playwright/Chromium is no longer used, so there is no `playwright install` step.

## Requirements

- [Python 3.11+](https://www.python.org/downloads/)
- [Node.js 20+](https://nodejs.org/) (comes with npm)
- Git

## Setup

```bash
git clone <this-repo-url>
cd Sentiment-Analyzer
```

### 1. Backend (terminal 1)

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate        # Windows Git Bash
# .venv\Scripts\Activate.ps1         # Windows PowerShell
# source .venv/bin/activate          # macOS / Linux
pip install -r requirements.txt
cp .env.example .env                 # PowerShell: copy .env.example .env
uvicorn app.main:app --reload --env-file .env
```

The API runs at http://127.0.0.1:8000 (interactive docs at http://127.0.0.1:8000/docs).

Demo mode (catalogue products only, never fetches Flipkart) runs on its own port, 8001, so it can run next to the live backend:

```bash
FORCE_FALLBACK=1 uvicorn app.main:app --reload --port 8001    # PowerShell: $env:FORCE_FALLBACK=1; uvicorn app.main:app --reload --port 8001
```

### 2. Frontend (terminal 2)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000.

The frontend talks to the live backend at `http://127.0.0.1:8000` by default. To use the demo backend instead, set `NEXT_PUBLIC_API_URL=http://127.0.0.1:8001` in `frontend/.env.local` and restart `npm run dev`.

## Configuration (`backend/.env`)

All settings are optional.

| Variable | What it does |
|---|---|
| `GROQ_API_KEY` | Free key from https://console.groq.com/keys. Used for the AI summary. |
| `GEMINI_API_KEY` | Free key from https://aistudio.google.com/apikey. Used if Groq is missing or fails. |
| `LLM_PROVIDERS` | Order the providers are tried in (default `groq,gemini`). |
| `GROQ_MODEL` / `GEMINI_MODEL` | Override the model id if a provider retires the default. |
| `FORCE_FALLBACK` | `0` (default): fetch reviews live from Flipkart. `1`: demo mode, catalogue products only. |

Without any API key, summaries use a built-in rule-based fallback, so the app still works.

## Live links vs. the catalogue

- **Catalogue products** (listed on the home page) are bundled with the repo and always work, even offline.
- **Any other Flipkart link** is fetched live in the background: one attempt, up to 50 reviews (at most 8 review pages, 90-second safety limit). If Flipkart shows a CAPTCHA or blocks the request (HTTP 403/429), the analysis fails with an error instead of retrying. Try again later or pick a catalogue product.
- If you see *"Live fetching is switched off on this server (demo mode)"*, the backend was started with `FORCE_FALLBACK=1`. Restart it with `--env-file .env` and `FORCE_FALLBACK=0`.

## Tests and checks

```bash
cd backend && pytest                       # backend tests (no network needed)
cd backend && python -m eval               # accuracy vs eval/gold.jsonl (add --llm to use the API keys)
cd frontend && npm run build && npm run lint
```

## Project docs

- [`SPEC.md`](SPEC.md): features, API contract, scraping architecture
- [`CLAUDE.md`](CLAUDE.md): rules for coding agents working on this repo
