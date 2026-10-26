"""The tower router — one OpenAI-compatible endpoint, local-first.

Resolve order for a request to model X:
    X → other local chat models (preference order) → alive cloud providers
Failure to *open* the stream advances the chain; once tokens flow we commit to
that upstream (mid-stream failover would duplicate tokens).

Every app on this laptop points here (the original "ONE tower endpoint" rule):
    base_url = http://127.0.0.1:7425/v1   key = tower
"""
from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

import httpx

from . import providers as prov
from . import secrets as sec
from . import state

CLOUD_PREFIXES = {p["id"] for p in prov.CLOUD_PROVIDERS}
TOWER_KEY = "tower"

_fallback_model_cache: dict[str, str] = {}   # provider id -> chosen model id


def resolve(model: str | None) -> dict[str, Any] | None:
    """-> {base, key, model, provider, tier} or None when nothing can serve it."""
    model = model or state.load().get("default_model") or "auto"
    if model == "auto":
        model = state.load().get("default_model", "campus/penny:latest")

    prefix = model.split("/")[0]
    if prefix in CLOUD_PREFIXES:
        for p in prov.CLOUD_PROVIDERS:
            if p["id"] == prefix and p.get("enabled") and p.get("base"):
                k = sec.get(p["file"])
                if not k:
                    return None
                mid = model.split("/", 1)[1]
                return {"base": p["base"], "key": k, "model": mid,
                        "provider": p["id"], "tier": "cloud"}
        return None

    la = prov.check_localai()
    if model in la.get("models", []):
        return {"base": prov.LOCALAI_BASE, "key": "local", "model": model,
                "provider": "localai", "tier": "local"}

    ol = prov.check_ollama()
    if model in ol.get("models", []) or ol.get("alive"):
        return {"base": prov.OLLAMA_BASE, "key": "ollama", "model": model,
                "provider": "ollama", "tier": "local"}
    return None


def chain(model: str | None) -> list[dict[str, Any]]:
    """Ordered candidates: selected, sibling local chat models, cloud.

    GPU-headroom guard (2026-10-27, seen live): an Ollama model that loads
    while the GPU is full lands in SYSTEM RAM — penny ate 5.6 GB that way and
    choked the laptop. So Ollama *fallbacks* are skipped when VRAM headroom
    is gone; the explicitly selected model (first candidate) is always
    honored — the user asked for it.
    """
    first = resolve(model)
    out: list[dict[str, Any]] = [first] if first else []
    seen = {first["model"] if first else None, first["provider"] if first else None}

    from . import metrics
    g = metrics.gpu()
    vram_free_mb = None
    if g.get("present") and g.get("vram_total_mb"):
        vram_free_mb = g["vram_total_mb"] - g["vram_used_mb"]
    room_ok = vram_free_mb is None or vram_free_mb > 2500

    for m in state.LOCAL_PREFERENCE:            # preferred locals next
        if not room_ok:
            break
        if (m, "ollama") in ((c["model"], c["provider"]) for c in out):
            continue
        c = resolve(m)
        if c and (c["model"], c["provider"]) not in seen and c["provider"] == "ollama":
            out.append(c)
            seen.add((c["model"], c["provider"]))

    if not state.load().get("fallback_to_cloud", True):
        return out

    for pid in prov.alive_cloud_order():        # then alive cloud providers
        p = next(x for x in prov.CLOUD_PROVIDERS if x["id"] == pid)
        mid = _best_cloud_model(pid)
        if not mid:
            continue
        k = sec.get(p["file"])
        if not k:
            continue
        out.append({"base": p["base"], "key": k, "model": mid,
                    "provider": pid, "tier": "cloud"})
    return out


def _best_cloud_model(provider: str) -> str | None:
    if provider in _fallback_model_cache:
        return _fallback_model_cache[provider]
    h = next((c for c in prov.check_all().get("cloud", []) if c["id"] == provider), {})
    good = [m for m in h.get("models", []) if prov._looks_good(m)]
    prefer = [m for m in good if any(t in m.lower() for t in
              ("llama-3.3", "llama-3.1-8b", "flash", "gemini-2", "qwen", "free",
               "deepseek"))]
    choice = (prefer or good)
    if not choice:
        return None
    _fallback_model_cache[provider] = choice[0]
    return choice[0]


def _headers(cand: dict[str, Any], stream: bool) -> dict[str, str]:
    h = {"Authorization": f"Bearer {cand['key']}", "Content-Type": "application/json"}
    if cand["provider"] == "openrouter":
        h["HTTP-Referer"] = "http://127.0.0.1:7425"
        h["X-Title"] = "AI Tower"
    return h


def _payload(cand: dict[str, Any], body: dict[str, Any], stream: bool) -> dict[str, Any]:
    p = dict(body)
    p["model"] = cand["model"]
    p["stream"] = stream
    # gemini compat + some aggregators dislike empty/system quirks
    if not p.get("messages"):
        p["messages"] = [{"role": "user", "content": "hi"}]
    return p


async def chat_stream(body: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
    """Yield OpenAI-style chunk dicts; fails over until first token.

    First yielded item is a meta event: {"tower": {...}} announcing who served it.
    """
    model = body.get("model")
    attempts: list[dict[str, Any]] = []
    candidates = chain(model)

    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=12.0)) as client:
        for cand in candidates:
            t0 = time.time()
            try:
                async with client.stream(
                    "POST", f"{cand['base'].rstrip('/')}/chat/completions",
                    headers=_headers(cand, True),
                    json=_payload(cand, body, True),
                ) as r:
                    if r.status_code >= 400:
                        detail = (await r.aread())[:200].decode(errors="replace")
                        attempts.append({"provider": cand["provider"],
                                         "model": cand["model"],
                                         "error": f"HTTP {r.status_code}: {detail}"})
                        _mark(cand, False, f"HTTP {r.status_code}")
                        continue
                    _mark(cand, True, None)
                    yield {"tower": {"provider": cand["provider"], "model": cand["model"],
                                     "tier": cand["tier"],
                                     "first_token_ms": int((time.time() - t0) * 1000)}}
                    committed = False
                    async for line in r.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            yield {"tower": {"done": True}}
                            return
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        committed = True
                        yield chunk
                    if committed:
                        yield {"tower": {"done": True}}
                        return
                    attempts.append({"provider": cand["provider"],
                                     "error": "stream closed before first token"})
            except Exception as e:  # noqa: BLE001 — failover is the point
                attempts.append({"provider": cand["provider"],
                                 "model": cand["model"], "error": str(e)[:180]})
                _mark(cand, False, str(e)[:120])
                continue

    yield {"error": {"message": "every upstream failed",
                     "attempts": attempts,
                     "hint": "check engines in the dashboard"}}


async def chat_json(body: dict[str, Any]) -> dict[str, Any]:
    """Non-streaming (agent tool calls). Same failover, returns full response."""
    candidates = chain(body.get("model"))
    attempts: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=12.0)) as client:
        for cand in candidates:
            try:
                r = await client.post(f"{cand['base'].rstrip('/')}/chat/completions",
                                      headers=_headers(cand, False),
                                      json=_payload(cand, body, False))
                if r.status_code >= 400:
                    attempts.append({"provider": cand["provider"],
                                     "error": f"HTTP {r.status_code}"})
                    _mark(cand, False, f"HTTP {r.status_code}")
                    continue
                data = r.json()
                data["_tower"] = {"provider": cand["provider"], "model": cand["model"]}
                return data
            except Exception as e:  # noqa: BLE001
                attempts.append({"provider": cand["provider"], "error": str(e)[:180]})
                _mark(cand, False, str(e)[:120])
    return {"error": {"message": "every upstream failed", "attempts": attempts}}


def _mark(cand: dict[str, Any], ok: bool, err: str | None) -> None:
    """Feed router outcomes back into provider health (dynamic failover brain)."""
    if cand["tier"] == "local" or cand["provider"] in CLOUD_PREFIXES:
        prov._record(f"cloud:{cand['provider']}" if cand["provider"] in CLOUD_PREFIXES
                     else cand["provider"], ok, None, err)
