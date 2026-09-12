# holehe phone web UI

Mobile-friendly dark UI for [holehe](https://github.com/megadose/holehe) on the
`perf/pr277-concurrency` fork branch (`-NP -T 3 --concurrency 10 --retries 2`).

## Setup

```bash
cd /path/to/holehe-web   # or this repo root if files live here
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn server:app --host 0.0.0.0 --port 8080
```

Open `http://localhost:8080` (or tunnel with cloudflared / ngrok for phones).

## API

- `GET /api/health` → `{ok: true}`
- `POST /api/scan` body `{ "email": "…" }` → `{ email, seconds, counts, results }`

Skips holehe’s `check_update`. Password-recovery modules are excluded (`-NP`).

## Disclaimer

Adults / OSINT only. Use only on emails you own or are authorized to investigate.
