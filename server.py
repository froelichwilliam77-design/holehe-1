"""Phone-friendly FastAPI UI for holehe (PR277 concurrency defaults)."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import trio
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from holehe.core import (
    get_functions,
    import_submodules,
    is_email,
    merge_results,
    modules_for_names,
    run_websites,
)

WEB_DIR = Path(__file__).resolve().parent / "web"

# Defaults matching: holehe -NP -T 3 --concurrency 10 --retries 2
TIMEOUT = 3
CONCURRENCY = 10
RETRIES = 2
RETRY_DELAY = 3.0

app = FastAPI(title="holehe web", docs_url=None, redoc_url=None)


class ScanRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)


def _status(row: dict) -> str:
    if row.get("rateLimit"):
        return "rate_limit"
    if row.get("error"):
        return "error"
    if row.get("exists"):
        return "used"
    return "not_used"


def _serialize(row: dict) -> dict:
    others = row.get("others")
    return {
        "name": row.get("name"),
        "domain": row.get("domain"),
        "status": _status(row),
        "exists": bool(row.get("exists")),
        "rateLimit": bool(row.get("rateLimit")),
        "error": bool(row.get("error")),
        "emailrecovery": row.get("emailrecovery"),
        "phoneNumber": row.get("phoneNumber"),
        "others": others if isinstance(others, dict) else None,
    }


async def _scan(email: str) -> dict:
    args = SimpleNamespace(nopasswordrecovery=True)
    modules = import_submodules("holehe.modules")
    websites = get_functions(modules, args)

    start = time.time()
    limits = httpx.Limits(
        max_connections=CONCURRENCY,
        max_keepalive_connections=CONCURRENCY,
    )
    client = httpx.AsyncClient(
        timeout=TIMEOUT,
        limits=limits,
        follow_redirects=True,
    )
    try:
        out = await run_websites(websites, email, client, CONCURRENCY)
        for attempt in range(1, RETRIES + 1):
            limited_names = [r["name"] for r in out if r.get("rateLimit")]
            if not limited_names:
                break
            retry_modules = modules_for_names(websites, limited_names)
            await trio.sleep(RETRY_DELAY)
            retry_conc = max(1, min(CONCURRENCY, max(3, CONCURRENCY // 2)))
            refreshed = await run_websites(
                retry_modules, email, client, retry_conc
            )
            out = merge_results(out, refreshed)
        out = sorted(out, key=lambda i: i["name"])
    finally:
        await client.aclose()

    results = [_serialize(r) for r in out]
    counts = {
        "used": sum(1 for r in results if r["status"] == "used"),
        "not_used": sum(1 for r in results if r["status"] == "not_used"),
        "rate_limit": sum(1 for r in results if r["status"] == "rate_limit"),
        "error": sum(1 for r in results if r["status"] == "error"),
        "total": len(results),
    }
    return {
        "email": email,
        "seconds": round(time.time() - start, 2),
        "counts": counts,
        "results": results,
    }


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "holehe-web"}


@app.post("/api/scan")
async def scan(body: ScanRequest):
    email = body.email.strip().lower()
    if not is_email(email):
        raise HTTPException(status_code=400, detail="Invalid email address")
    # holehe uses trio; run off the asyncio event loop
    try:
        return await asyncio.to_thread(trio.run, _scan, email)
    except Exception as exc:  # noqa: BLE001 — surface as 500 for UI
        raise HTTPException(status_code=500, detail=f"Scan failed: {exc}") from exc


@app.get("/")
async def index():
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
