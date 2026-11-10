# CLAUDE.md — Operational Rules for Coding Agents

E-Commerce Sentiment Analysis & Review Authenticity Tool. Single review source: Flipkart (Amazon.in was dropped, see SPEC §A.1).
**Read `SPEC.md` before any task.** It defines the features, directory layout, the `/api/v3` data contract, and the background-job scraping architecture.

---

## Tech Stack Commands

### Backend (`/backend`, Python 3.11+, FastAPI)
```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate        # Windows Git Bash  (PowerShell: .venv\Scripts\Activate.ps1)
pip install -r requirements.txt
cp .env.example .env                 # then fill in GROQ_API_KEY / GEMINI_API_KEY (both optional)
uvicorn app.main:app --reload --env-file .env   # dev server → http://127.0.0.1:8000  (docs at /docs)
pytest                               # full test suite
pytest tests/test_summarizer.py -v   # single module
python -m eval                       # accuracy vs eval/gold.jsonl (offline; --llm uses the API keys)
uvicorn app.demo:app --reload --port 8001   # demo mode on :8001: never scrape live (app.main is always live)
```

### Frontend (`/frontend`, Next.js App Router, TypeScript, Tailwind)
Next.js here is newer than most training data: read `frontend/AGENTS.md` and the guide in `frontend/node_modules/next/dist/docs/` before changing routing, data fetching or fonts.
```bash
cd frontend
npm install
npm run dev                          # dev server → http://localhost:3000
npm run build && npm run lint        # pre-commit check
```

---

## Agent Guardrails

1. **No live scraping loops.** Never run live scraping in an automated loop against Amazon or Flipkart URLs (this risks IP bans and wastes tokens). Always test scraper logic against local HTML snapshot files in `/backend/app/scraper/snapshots/` first. A single manual live check is allowed only when the user explicitly asks for one. Never attempt to solve or bypass a CAPTCHA. On detection, abort and fall back (SPEC §D).

2. **The API contract is frozen without a SPEC change.** Never modify the request or response structure of any `/api/v3` endpoint without updating `SPEC.md` first, because the Next.js frontend relies strictly on this contract. Any change must update all three together: `SPEC.md` §C, `backend/app/schemas.py`, and `frontend/src/types/analysis.ts`.

3. **Small, modular, tested.** Keep functions modular and under 80 lines. Write unit tests in `/backend/tests/` for every NLP and scoring module (Hinglish normalizer, sentiment, aspects/opinion units, use cases, trust, fulfillment, summarizer) before wiring it to FastAPI. Tests must not hit the network. Use snapshots, `seed_reviews.json`, or inline fixtures.

4. **Preserve negations and emojis.** During text preprocessing, never strip negation words (`not`, `never`, `no`, plus Hinglish `nahi`, `mat`, `na`) or emojis. They carry polarity ("not good", "👎", "😍"). Don't drop them as stopwords, and don't remove them in unicode/punctuation cleanup.

---

## Additional Conventions

- Live collection runs only inside a background job: one attempt that stops at 50 reviews, at most 8 review pages, a hard 90-second safety budget, immediate abort on CAPTCHA or block, then the catalogue fallback (SPEC §D). Never remove the budget or the page cap, raise them without a SPEC change, or add retries. The API request itself must never wait on a live scrape.
- Don't commit secrets. LLM API keys (`GROQ_API_KEY`, `GEMINI_API_KEY`) go in `backend/.env` (gitignored; template in `backend/.env.example`). The summarizer must keep its deterministic fallback for when no key is set or every provider fails.
- Frontend look: editorial cards on a light or dark theme (colour tokens in `frontend/src/app/globals.css`, never raw hex or Tailwind palette colours in components); no gradients, glows or decorative icons, and glass (translucency plus blur) only on the sticky nav; percentages always shown with their counts, never opaque scores (SPEC §A.1); every claim links to its reviews. Charts are plain CSS, print their numbers, never use colour alone, and new chart colours are checked in both themes. Desktop follows mockup C without its "Is it good for…" cards (they repeated the aspect rows) and with this hero: two columns sharing top and bottom edges, title then verdict then ratings on the left, photo and all its thumbnails on the right (verdict and ratings sit side by side when there are no photos). Phones follow mockup E (verdict card, aspect rows that open a bottom sheet).
- `backend/app/data/cache.sqlite` and `.venv/` are gitignored. `seed_reviews.json` and `scraper/snapshots/*.html` are committed.
