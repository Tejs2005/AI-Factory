"""AI Tower server — FastAPI app: dashboard UI + OpenAI-compatible gateway +
control plane (apps, approvals, agent). Loopback only.

Run:  python3 -m tower.server        (or `ai-tower up`)
"""
from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import agent, apps as apps_mod, metrics, providers as prov, router, rules as rules_mod, state
from .paths import (STATIC_DIR, TOWER_HOST, TOWER_PORT, ensure_dirs)

started_at = time.time()


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_dirs()
    agent.write_needle_tools()
    asyncio.get_event_loop().create_task(_warm_health())
    asyncio.get_event_loop().create_task(_restore_keep())
    yield
    from . import browser
    await browser.close()                      # never leave a chromium behind


async def _warm_health():
    await asyncio.to_thread(prov.check_all)
    await asyncio.to_thread(apps_mod.all_status)


async def _restore_keep():
    """Re-pin the models the user left switched ON before the last restart."""
    keep = state.kept_on()
    if not keep:
        return
    await asyncio.sleep(1.5)                     # let ollama settle first
    res = await asyncio.to_thread(metrics.restore_pins, keep)
    print(f"[tower] keep-set restored: {len(res['loaded'])}/{res['requested']} "
          f"pinned: {', '.join(res['loaded'])}", flush=True)


app = FastAPI(title="AI Tower", lifespan=lifespan, docs_url="/api/docs",
              openapi_url="/api/openapi.json")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def sse(events) -> StreamingResponse:
    async def gen():
        async for ev in events:
            yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# ── dashboard API ────────────────────────────────────────────────────────────
@app.get("/api/status")
async def api_status() -> dict[str, Any]:
    health = await asyncio.to_thread(prov.check_all)
    reg = await asyncio.to_thread(apps_mod.all_status)
    st = state.load()
    return {
        "uptime_sec": int(time.time() - started_at),
        "ollama": health["local"]["ollama"],
        "localai": health["local"]["localai"],
        "needle": {"alive": agent._needle_alive()},
        "cloud": health["cloud"],
        "gpu": await asyncio.to_thread(metrics.gpu),
        "speech": {k: {"alive": v.get("alive"), "models": v.get("models")}
                   for k, v in (health.get("speech") or {}).items()},
        "apps": [{"id": a["id"], "status": a["status"]} for a in reg],
        "default_model": st.get("default_model"),
        "agent_model": st.get("agent_model"),
        "pending_approvals": len(state.pending_approvals()),
    }


@app.get("/api/models")
async def api_models() -> dict[str, Any]:
    cat = await asyncio.to_thread(prov.catalogue)
    st = state.load()
    keep = set(st.get("kept_on", []))
    loaded = {m["name"]: m for m in await asyncio.to_thread(metrics.loaded_models)}
    for m in cat:
        m["default"] = m["id"] == st.get("default_model")
        m["agent"] = m["id"] == st.get("agent_model")
        # footprint + power switch (local Ollama models only)
        lm = loaded.get(m["id"])
        m["loaded"] = bool(lm)
        m["kept_on"] = m["id"] in keep
        if lm:
            m["vram_gb"] = lm.get("vram_gb")
            m["ram_gb"] = lm.get("ram_gb")
            m["size_gb"] = lm.get("size_gb")
            m["pinned"] = lm.get("pinned")
            m["params"] = lm.get("params")
            m["quant"] = lm.get("quant")
    return {"models": cat, "default_model": st.get("default_model"),
            "agent_model": st.get("agent_model"),
            "deep_model": st.get("deep_model"),
            "fallback_to_cloud": st.get("fallback_to_cloud", True),
            "kept_on": sorted(keep),
            "loaded": list(loaded.keys())}


@app.post("/api/models/switch")
async def api_switch(req: Request) -> dict[str, Any]:
    body = await req.json()
    model = (body or {}).get("model", "").strip()
    if not model:
        return JSONResponse({"ok": False, "error": "no model"}, status_code=400)
    state.save({"default_model": model})
    return {"ok": True, "default_model": model}


@app.post("/api/models/agent")
async def api_set_agent(req: Request) -> dict[str, Any]:
    body = await req.json()
    state.save({"agent_model": (body or {}).get("model", "")})
    return {"ok": True, "agent_model": state.load().get("agent_model")}


@app.post("/api/models/fallback")
async def api_fallback(req: Request) -> dict[str, Any]:
    body = await req.json()
    state.save({"fallback_to_cloud": bool((body or {}).get("enabled", True))})
    return {"ok": True, "fallback_to_cloud": state.load().get("fallback_to_cloud")}


# ── resource monitor: CPU / RAM / GPU + per-model footprint ──────────────────
@app.get("/api/resources")
async def api_resources() -> dict[str, Any]:
    snap = await asyncio.to_thread(metrics.snapshot)
    snap["kept_on"] = state.kept_on()
    return snap


@app.post("/api/models/keep")
async def api_keep(req: Request) -> dict[str, Any]:
    """The per-model power switch: keep a local model resident (ON) or
    unload it from RAM/VRAM (OFF). The choice persists across restarts."""
    body = await req.json()
    model = (body or {}).get("model", "").strip()
    on = bool((body or {}).get("on", True))
    if not model:
        return JSONResponse({"ok": False, "error": "no model"}, status_code=400)
    # only models Ollama actually knows have a keep_alive switch
    try:
        tags = metrics._http_json(f"{metrics.OLLAMA_URL}/api/tags")
        names = {t.get("name") for t in tags.get("models", [])}
    except Exception:  # noqa: BLE001
        names = set()
    if names and model not in names and model.split(":")[0] not in names:
        return JSONResponse(
            {"ok": False, "error": "not a local Ollama model"}, status_code=400)
    res = await asyncio.to_thread(metrics.set_keep, model, on)
    if res.get("ok"):
        state.set_kept(model, on)
    res["kept_on"] = state.kept_on()
    return res


@app.get("/api/keys")
async def api_keys() -> dict[str, Any]:
    health = await asyncio.to_thread(prov.check_all)
    out = []
    for c in health["cloud"]:
        out.append({"id": c["id"], "enabled": c.get("enabled"),
                    "alive": c.get("alive"), "note": c.get("note"),
                    "key_mask": c.get("key_mask", "—"),
                    "error": c.get("last_error"),
                    "models": len(c.get("models") or []),
                    "checked": c.get("checked"),
                    "base": c.get("base") or "—"})
    return {"providers": out}


@app.post("/api/keys/recheck")
async def api_keys_recheck() -> dict[str, Any]:
    health = await asyncio.to_thread(prov.check_all, True)
    return {"ok": True, "alive": sum(1 for c in health["cloud"] if c.get("alive"))}


@app.post("/api/chat")
async def api_chat(req: Request):
    body = await req.json()
    prompt = (body or {}).get("prompt", "").strip()
    if not prompt:
        return JSONResponse({"error": "empty prompt"}, status_code=400)
    history = list((body or {}).get("history") or [])[-12:]
    history.append({"role": "user", "content": prompt})
    model = (body or {}).get("model")       # None → tower default

    async def events():
        parts = []
        async for chunk in router.chat_stream({"model": model, "messages": history}):
            if "tower" in chunk:
                # the router's closing {"tower": {"done": true}} must NOT reach
                # the dashboard: the chat renderer treats a tower event as the
                # "who answered" label and would wipe the finished reply
                t = chunk.get("tower")
                if not (isinstance(t, dict) and t.get("done")):
                    yield chunk
                continue
            if "error" in chunk:
                yield chunk
                return
            for ch in chunk.get("choices") or []:
                delta = ch.get("delta") or {}
                if (t := delta.get("content")):
                    parts.append(t)
                    yield {"type": "token", "text": t}
                if (tc := delta.get("tool_calls")):
                    yield {"type": "tool_calls", "tool_calls": tc}
        hist = state.load().get("history", [])
        hist.append({"t": time.time(), "model": model or state.load().get("default_model"),
                     "prompt": prompt[:200],
                     "reply": "".join(parts)[:400]})
        state.save({"history": hist[-60:]})
        yield {"type": "done"}
    return sse(events())


# ── control plane: apps + approvals ─────────────────────────────────────────
@app.get("/api/apps")
async def api_apps() -> dict[str, Any]:
    return {"apps": await asyncio.to_thread(apps_mod.all_status),
            "log": apps_mod.recent_log(40)}


@app.post("/api/apps/{app_id}/launch")
async def api_launch(app_id: str, req: Request):
    body = await req.json() if await req.body() else {}
    source = (body or {}).get("source", "user")
    if source == "agent":
        # agent route goes through approvals instead of this endpoint
        return JSONResponse({"ok": False, "error": "use approval flow"},
                            status_code=403)
    return await asyncio.to_thread(apps_mod.launch, app_id, source)


@app.post("/api/apps/{app_id}/stop")
async def api_stop(app_id: str, req: Request):
    body = await req.json() if await req.body() else {}
    return await asyncio.to_thread(apps_mod.stop, app_id,
                                   (body or {}).get("source", "user"))


@app.get("/api/approvals")
async def api_approvals() -> dict[str, Any]:
    return {"pending": state.pending_approvals()}


# ── brain library: skills + rules ────────────────────────────────────────────
@app.get("/api/skills")
async def api_skills(q: str = "", category: str = "", limit: int = 40) -> dict[str, Any]:
    from . import skills as sk
    if q:
        items = await asyncio.to_thread(sk.search, q, limit)
    else:
        items = await asyncio.to_thread(sk.index)
        if category:
            items = [i for i in items if i.get("category") == category][:limit]
        else:
            items = items[:limit]
    return {"skills": items, "stats": await asyncio.to_thread(sk.stats)}


@app.get("/api/skills/{name}")
async def api_skill(name: str) -> dict[str, Any]:
    from . import skills as sk
    return await asyncio.to_thread(sk.read, name)


@app.get("/api/rules")
async def api_rules(hard_only: bool = False) -> dict[str, Any]:
    return {"rules": await asyncio.to_thread(rules_mod.list_rules, hard_only),
            "stats": await asyncio.to_thread(rules_mod.stats),
            "constitution": await asyncio.to_thread(rules_mod.hard_statements)}


@app.get("/api/rules/{rule}")
async def api_rule(rule: str) -> dict[str, Any]:
    return await asyncio.to_thread(rules_mod.read, rule)


@app.post("/api/approvals/{approval_id}")
async def api_decide(approval_id: str, req: Request):
    body = await req.json()
    body = body or {}
    # answer carries the free-form reply for ask_user questions (may be "")
    answer = str(body.get("answer") or "").strip() or None
    res = state.decide_approval(approval_id, bool(body.get("approve")), answer)
    if not res:
        return JSONResponse({"ok": False, "error": "no such pending approval"},
                            status_code=404)
    return {"ok": True, "approval": res}


# ── browser harness — the local models' hands ────────────────────────────────
@app.get("/api/browser")
async def api_browser_state() -> dict[str, Any]:
    from . import browser
    return await browser.alive()


@app.post("/api/browser/{action}")
async def api_browser(action: str, req: Request) -> dict[str, Any]:
    """Dashboard-side control (Tejas driving directly = same trust as app
    Start buttons). The AGENT never reaches this endpoint — its browser calls
    go through the approval gate in agent.py (browser_submit is gated)."""
    from . import browser
    try:
        body = await req.json()
    except Exception:  # noqa: BLE001 — empty body is fine
        body = {}
    body = body or {}
    try:
        if action == "open":
            return await browser.open_url(str(body.get("url", "")))
        if action == "read":
            return await browser.read_page()
        if action == "click":
            return await browser.click(str(body.get("target", "")))
        if action == "type":
            return await browser.type_text(str(body.get("target", "")),
                                           str(body.get("text", "")))
        if action == "submit":
            return await browser.submit(str(body.get("target", "")))
        if action == "back":
            return await browser.back()
        if action == "shot":
            return await browser.shot(str(body.get("name", "")))
        if action == "tabs":
            return await browser.tabs()
        if action == "close":
            await browser.close()
            return {"ok": True, "closed": True}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:300]}
    return JSONResponse({"ok": False, "error": f"unknown action {action}"},
                        status_code=404)


# ── the operator agent ──────────────────────────────────────────────────────
@app.post("/api/agent/run")
async def api_agent_run(req: Request):
    body = await req.json()
    task = ((body or {}).get("task") or "").strip()
    if not task:
        return JSONResponse({"error": "no task"}, status_code=400)
    mode = (body or {}).get("mode", "auto")
    ans_model = (body or {}).get("answer_model")
    return sse(agent.run(task, mode=mode, answer_model=ans_model))


@app.post("/api/agent/needle/tools")
async def api_needle_tools() -> dict[str, Any]:
    agent.write_needle_tools()
    return {"ok": True, "path": str(agent.NEEDLE_TOOLS_FILE)}


# ── logs ─────────────────────────────────────────────────────────────────────
@app.get("/api/logs")
async def api_logs(n: int = 150) -> dict[str, Any]:
    from .paths import LOGS_DIR
    out: dict[str, Any] = {"apps": apps_mod.recent_log(n)}
    for name in ("needle.log", "localai.out", "server.out"):
        p = LOGS_DIR / name
        if p.exists():
            out[name] = p.read_text(errors="replace").splitlines()[-n:]
    return out


# ── OpenAI-compatible gateway (for Jan, dyad, anything) ─────────────────────
@app.post("/v1/chat/completions")
async def v1_chat(req: Request):
    body = await req.json()
    if body.get("stream"):
        async def passthrough():
            async for chunk in router.chat_stream(body):
                yield f"data: {json.dumps(chunk, ensure_ascii=False, default=str)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(passthrough(), media_type="text/event-stream")
    return await router.chat_json(body)


@app.get("/v1/models")
async def v1_models():
    cat = await asyncio.to_thread(prov.catalogue)
    return {"object": "list",
            "data": [{"id": m["id"], "object": "model",
                      "owned_by": m["engine"]} for m in cat]}


@app.get("/health")
async def health():
    return {"ok": True, "tower": "up", "uptime_sec": int(time.time() - started_at)}


# ── studio (speech): voxcpm2 = LocalAI specialty, Kokoro = CPU podman ────────
async def _speech_to_file(r: "httpx.Response") -> dict[str, Any]:
    """Write an audio engine's mp3 bytes under static/audio, serve via /static."""
    from .paths import STATIC_DIR
    import uuid
    audio_dir = STATIC_DIR / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    fn = audio_dir / f"tts-{uuid.uuid4().hex[:8]}.mp3"
    fn.write_bytes(r.content)
    # served by the /static mount (StaticFiles blocks traversal for us)
    return {"ok": True, "file": f"/static/audio/{fn.name}"}


@app.post("/api/studio/tts")
async def studio_tts(req: Request):
    body = await req.json()
    text = ((body or {}).get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "no text"}, status_code=400)
    voice = (body or {}).get("voice", "")
    model = (body or {}).get("model", "")
    if model == "voxcpm2" or voice == "voxcpm2":
        la = prov.check_localai()
        if not la.get("alive"):
            return JSONResponse({"error": "LocalAI is down — start it in Apps"}, 503)
        try:
            async with httpx.AsyncClient(timeout=180.0) as c:
                r = await c.post(f"{prov.LOCALAI_BASE}/audio/speech",
                                 headers={"Authorization": "Bearer local"},
                                 json={"model": "voxcpm2", "input": text,
                                       "response_format": "mp3"})
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"error": str(e)[:300]}, 502)
    else:
        sp = prov.speech_engine("speaches")
        h = prov.check_speech(sp)
        if not h.get("alive"):
            return JSONResponse(
                {"error": "speaches is down — start it in Apps "
                          "(podman container, CPU)"}, 503)
        try:
            async with httpx.AsyncClient(timeout=180.0) as c:
                r = await c.post(f"{sp['base']}/audio/speech",
                                 json={"model": "speaches-ai/Kokoro-82M-v1.0-ONNX-fp16",
                                       "input": text,
                                       "voice": voice or "af_heart",
                                       "response_format": "mp3"})
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"error": str(e)[:300]}, 502)
    if r.status_code >= 400:
        return JSONResponse({"error": f"engine: HTTP {r.status_code}",
                             "detail": r.text[:300]}, 502)
    return await _speech_to_file(r)


@app.post("/api/studio/stt")
async def studio_stt(req: Request):
    """Audio → text via speaches (faster-whisper). Multipart with a 'file'
    field; the engine demands a 'model' field, so the tower injects its
    default when the client didn't send one."""
    sp = prov.speech_engine("speaches")
    h = prov.check_speech(sp)
    if not h.get("alive"):
        return JSONResponse({"error": "speaches is down — start it in Apps "
                                      "(podman container, CPU)"}, 503)
    form = await req.form()
    up = form.get("file")
    if up is None or isinstance(up, str):
        return JSONResponse({"error": "send multipart/form-data with a "
                                      "'file' audio field"}, 400)
    data = await up.read()
    if not data:
        return JSONResponse({"error": "empty file"}, 400)
    model = str(form.get("model") or "Systran/faster-whisper-tiny")
    try:
        async with httpx.AsyncClient(timeout=300.0) as c:
            r = await c.post(
                f"{sp['base']}/audio/transcriptions",
                files={"file": (up.filename or "audio", data,
                                up.content_type or "application/octet-stream")},
                data={"model": model})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)[:300]}, 502)
    if r.status_code >= 400:
        return JSONResponse({"error": f"engine: HTTP {r.status_code}",
                             "detail": r.text[:300]}, 502)
    return {"ok": True, **_safe_json(r)}


def _safe_json(r: "httpx.Response") -> dict[str, Any]:
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return {"text": r.text[:2000]}


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(errors="replace"))


def main() -> None:
    import uvicorn
    ensure_dirs()
    uvicorn.run(app, host=TOWER_HOST, port=TOWER_PORT, log_level="warning",
                access_log=False)


if __name__ == "__main__":
    main()
