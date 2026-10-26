"""Provider registry: two local engines + every cloud key in the store.

Health model: each provider has alive/latency/last_error/checked, refreshed
lazily (on demand, min interval). No key value is ever exposed from here —
only masked forms via describe().
"""
from __future__ import annotations

import threading
import time
from typing import Any

import httpx

from . import secrets as sec
from .paths import LOCALAI_BASE, OLLAMA_BASE

REFRESH_INTERVAL = 45.0  # seconds before a health check is re-run


def _cloudflare_base() -> str | None:
    """Workers AI needs the account id in the path:
    /client/v4/accounts/{account_id}/ai/v1  (OpenAI-compatible).

    The token itself verifies fine but has no Account Read scope (REST
    /accounts → empty, GraphQL → "not authorized"), so the id must come from
    secrets/cloudflare.txt as an `account_id=…` line (it sits in the dashboard
    URL). Returns None until that line exists → provider shows "no endpoint".
    """
    aid = sec.account_id_of("cloudflare.txt")
    if not aid:
        return None
    return f"https://api.cloudflare.com/client/v4/accounts/{aid}/ai/v1"


# The order decides cloud fallback preference (fast + generous free tiers first).
CLOUD_PROVIDERS: list[dict[str, Any]] = [
    {"id": "groq", "base": "https://api.groq.com/openai/v1", "file": "groq.txt",
     "note": "very fast, free tier", "enabled": True},
    {"id": "openrouter", "base": "https://openrouter.ai/api/v1", "file": "openrouter.txt",
     "note": "many models incl. :free", "enabled": True},
    {"id": "gemini", "base": "https://generativelanguage.googleapis.com/v1beta/openai/",
     "file": "google-gemini.txt", "note": "google flash models", "enabled": True},
    {"id": "cloudflare", "base": _cloudflare_base(), "file": "cloudflare.txt",
     "note": "Workers AI 10k neurons/day", "enabled": True},
    {"id": "nscale", "base": "https://inference.api.nscale.com/v1", "file": "nscale cloud.txt",
     "note": "5 USD credit", "enabled": True},
    {"id": "anyapi", "base": sec.endpoint_of("anyapi.txt") or "https://api.anyapi.ai/v1",
     "file": "anyapi.txt", "note": "aggregator", "enabled": True},
    {"id": "cohere", "base": "https://api.cohere.ai/compatibility/v1", "file": "cohere.txt",
     "note": "2 tokens in file", "enabled": True},
    # benched / dead — shown in the UI, never routed to
    {"id": "nvidia", "base": "https://integrate.api.nvidia.com/v1", "file": "nvidia.txt",
     "note": "BENCHED: ~227 s/reply, beats timeouts", "enabled": False},
    {"id": "llm7", "base": None, "file": "llm7.io.txt",
     "note": "DEAD: HTTP 402 free quota exhausted", "enabled": False},
    {"id": "zai-plan", "base": None, "file": "zai-coding-plan.txt",
     "note": "DEAD: HTTP 429 plan exhausted", "enabled": False},
    {"id": "requesty", "base": None, "file": "requesty.txt",
     "note": "DEAD: HTTP 402 no balance", "enabled": False},
]

LOCAL_ENGINES = [
    {"id": "ollama", "base": OLLAMA_BASE, "label": "Ollama", "port": 11434},
    {"id": "localai", "base": LOCALAI_BASE, "label": "LocalAI", "port": 8080},
]

# ── speech engine (rootless podman, CPU on purpose) ──────────────────────────
# speaches (MIT) runs as a podman CPU container speaking the OpenAI audio API
# for BOTH directions: Kokoro TTS (/audio/speech) and faster-whisper STT
# (/audio/transcriptions). CPU only — the GPU is bonsai's, and a second GPU
# claimant is how this laptop choked before. (Kokoro-FastAPI's own images went
# private on GHCR 2026-10-26, so the research doc's other ADOPT pick can't be
# pulled; speaches ships Kokoro itself, one container, same endpoints.)
SPEECH_ENGINES = [
    {"id": "speaches", "base": "http://127.0.0.1:8000/v1", "port": 8000,
     "label": "speaches (Kokoro TTS + whisper STT)",
     "note": "one CPU container: /audio/speech + /audio/transcriptions"},
]


def speech_engine(engine_id: str) -> dict[str, Any] | None:
    return next((e for e in SPEECH_ENGINES if e["id"] == engine_id), None)

# models served by LocalAI and their kind (chat | tts | video | image)
LOCALAI_KINDS = {
    "voxcpm2": "tts",
    "wan-2.1-t2v-1.3b-ggml": "video",
}

# The deep tier: heavier local models kept for hard reasoning tasks (the
# Operator can answer with them on demand). Not the everyday default — penny
# stays the fast chat brain. One place, so the UI switcher and any tooling
# agree on what "deep" means.
DEEP_MODELS = {"qwen3.5:4b"}

# Gemini ids this key can actually serve (its /models list is stale: the
# "models/..." entries 404 with "no longer available to new users")
GEMINI_OK = ["gemini-flash-lite-latest", "gemini-flash-latest",
             "gemma-4-26b-a4b-it"]

_lock = threading.Lock()
_health: dict[str, dict[str, Any]] = {}


def _fresh(key: str) -> dict[str, Any] | None:
    h = _health.get(key)
    if h and time.time() - h.get("checked", 0) < REFRESH_INTERVAL:
        return h
    return None


def _record(key: str, alive: bool, latency: float | None = None,
            error: str | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    with _lock:
        h = _health.setdefault(key, {})
        h.update({"alive": alive, "latency_ms": latency, "last_error": error,
                  "checked": time.time()})
        if extra:
            h.update(extra)
        return dict(h)


def _get(client: httpx.Client, url: str, headers: dict | None = None, **kw) -> httpx.Response:
    return client.get(url, headers=headers or {}, timeout=kw.pop("timeout", 12.0), **kw)


# ── local engines ─────────────────────────────────────────────────────────────
def check_ollama(force: bool = False) -> dict[str, Any]:
    if not force and (h := _fresh("ollama")):
        return h
    t0 = time.time()
    try:
        with httpx.Client() as c:
            r = _get(c, "http://127.0.0.1:11434/api/tags")
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
        return _record("ollama", True, round((time.time() - t0) * 1000),
                       extra={"models": models})
    except Exception as e:  # noqa: BLE001 — health probes never raise
        return _record("ollama", False, None, error=str(e)[:160], extra={"models": []})


def check_localai(force: bool = False) -> dict[str, Any]:
    if not force and (h := _fresh("localai")):
        return h
    t0 = time.time()
    try:
        with httpx.Client() as c:
            r = _get(c, f"{LOCALAI_BASE}/models",
                     headers={"Authorization": "Bearer local"})
            r.raise_for_status()
            models = [m["id"] for m in r.json().get("data", [])]
        return _record("localai", True, round((time.time() - t0) * 1000),
                       extra={"models": models})
    except Exception as e:  # noqa: BLE001
        return _record("localai", False, None, error=str(e)[:160], extra={"models": []})


# ── speech containers + cloud providers ──────────────────────────────────────
def check_speech(e: dict[str, Any], force: bool = False) -> dict[str, Any]:
    """Health probe for a speech container (GET its /models)."""
    key = f"speech:{e['id']}"
    if not force and (h := _fresh(key)):
        return h
    t0 = time.time()
    try:
        with httpx.Client() as c:
            r = _get(c, f"{e['base']}/models")
            r.raise_for_status()
            models = [m.get("id", "") for m in r.json().get("data", [])]
        return _record(key, True, round((time.time() - t0) * 1000),
                       extra={"models": models, "note": e.get("note")})
    except Exception as ex:  # noqa: BLE001
        return _record(key, False, None, error=str(ex)[:160],
                       extra={"models": [], "note": e.get("note")})


def check_cloud(p: dict[str, Any], force: bool = False) -> dict[str, Any]:
    key = f"cloud:{p['id']}"
    if not p.get("enabled"):
        return _record(key, False, None, error=p.get("note", "disabled"),
                       extra={"models": [], "note": p.get("note")})
    if not force and (h := _fresh(key)):
        return h
    k = sec.get(p["file"])
    if not k:
        return _record(key, False, None, error="no key",
                       extra={"models": [], "note": p.get("note")})
    if not p.get("base"):
        return _record(key, False, None, error="no endpoint — add account_id= line"
                                               f" to secrets/{p['file']}",
                       extra={"models": [], "note": p.get("note"),
                              "key_mask": sec.mask(k)})
    t0 = time.time()
    try:
        with httpx.Client() as c:
            r = _get(c, f"{p['base'].rstrip('/')}/models",
                     headers={"Authorization": f"Bearer {k}"})
            r.raise_for_status()
            ids = [m.get("id", "") for m in r.json().get("data", [])]
        return _record(key, True, round((time.time() - t0) * 1000),
                       extra={"models": ids, "note": p.get("note"),
                              "key_mask": sec.mask(k)})
    except httpx.HTTPStatusError as e:
        return _record(key, False, None, error=f"HTTP {e.response.status_code}",
                       extra={"models": [], "note": p.get("note"),
                              "key_mask": sec.mask(k)})
    except Exception as e:  # noqa: BLE001
        return _record(key, False, None, error=str(e)[:160],
                       extra={"models": [], "note": p.get("note"),
                              "key_mask": sec.mask(k)})


def check_all(force: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {"local": {}, "cloud": [], "speech": {}}
    out["local"]["ollama"] = check_ollama(force)
    out["local"]["localai"] = check_localai(force)
    for e in SPEECH_ENGINES:
        out["speech"][e["id"]] = check_speech(e, force)
    for p in CLOUD_PROVIDERS:
        h = check_cloud(p, force)
        out["cloud"].append({"id": p["id"], "base": p["base"], "enabled": p["enabled"],
                             "note": p.get("note"), **h})
    return out


# ── model catalogue (what the switcher shows) ─────────────────────────────────
def catalogue() -> list[dict[str, Any]]:
    """All models across engines, local ones first — this feeds the UI switcher."""
    models: list[dict[str, Any]] = []
    ol = check_ollama()
    for name in ol.get("models", []):
        models.append({
            "id": name, "engine": "ollama",
            "tier": "deep" if name in DEEP_MODELS else "local",
            "kind": "tts" if "audio" in name else ("vision" if "vl" in name else "chat"),
        })
    la = check_localai()
    for mid in la.get("models", []):
        models.append({
            "id": mid, "engine": "localai", "tier": "local",
            "kind": LOCALAI_KINDS.get(mid, "chat"),
        })
    # cloud: only healthy, enabled providers — capped so the picker stays sane
    for p in CLOUD_PROVIDERS:
        h = _health.get(f"cloud:{p['id']}", {})
        if not h.get("alive"):
            continue
        curated = [m for m in h.get("models", []) if _looks_good(m)][:6]
        if p["id"] == "gemini":
            # Google lists ids as "models/..." and most are retired for this key —
            # show the verified-answer set instead (see GEMINI_OK)
            curated = GEMINI_OK
        for m in curated:
            models.append({"id": f"{p['id']}/{m.removeprefix('models/')}",
                           "engine": p["id"], "tier": "cloud", "kind": "chat"})
    return models


def _looks_good(mid: str) -> bool:
    m = mid.lower()
    if any(bad in m for bad in ("whisper", "tts", "embed", "rerank", "moderation",
                                "image", "audio", "realtime", "guard")):
        return False
    return True


def alive_cloud_order() -> list[str]:
    """Provider ids that are alive, in fallback preference order."""
    order = []
    for p in CLOUD_PROVIDERS:
        if p.get("enabled") and _health.get(f"cloud:{p['id']}", {}).get("alive"):
            order.append(p["id"])
    return order


def describe() -> dict[str, Any]:
    """Everything the status API needs (masked keys only)."""
    h = check_all()
    return h
