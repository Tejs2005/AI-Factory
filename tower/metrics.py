"""Resource monitor: CPU / RAM / GPU, and per-model VRAM-RAM footprint.

Sources
- CPU + memory : psutil (already installed, no new dependency)
- GPU          : nvidia-smi (the laptop has an RTX 3070)
- model VRAM   : Ollama `GET /api/ps` — `size` (RAM) vs `size_vram` (VRAM),
                 plus `expires_at` (year 2319 = pinned by keep_alive -1).

Keep-alive switches live here too: `POST /api/generate` with `keep_alive: -1`
(load + pin) or `0` (unload). The chosen set is persisted in tower.json state
by the server layer so it survives a restart.
"""
from __future__ import annotations

import json
import subprocess
import time
from typing import Any

from .paths import OLLAMA_URL

try:                                     # optional; tower still works without it
    import psutil  # type: ignore
except Exception:                        # noqa: BLE001
    psutil = None  # type: ignore

_last_cpu: tuple[float, float] | None = None   # (global%, per-core avg %)


# ── CPU / RAM ────────────────────────────────────────────────────────────────
def _cpu() -> dict[str, Any]:
    if psutil is None:
        return {"pct": None, "cores": 0, "threads": 0, "per_core": []}
    global _last_cpu
    # interval=None → delta since the previous call (cheap, non-blocking)
    per = psutil.cpu_percent(interval=None, percpu=True)
    total = psutil.cpu_percent(interval=None)
    if _last_cpu is None and total == 0.0:      # first call: force a real sample
        total = psutil.cpu_percent(interval=0.3)
        per = psutil.cpu_percent(interval=None, percpu=True)
    _last_cpu = (total, 0.0)
    freq = psutil.cpu_freq()
    return {
        "pct": round(float(total), 1),
        "per_core": [round(float(p), 1) for p in per],
        "cores": psutil.cpu_count(logical=False) or 0,
        "threads": psutil.cpu_count() or 0,
        "ghz": round((freq.max or freq.current) / 1000, 2) if freq else None,
    }


def _mem() -> dict[str, Any]:
    if psutil is None:
        return {}
    m = psutil.virtual_memory()
    s = psutil.swap_memory()
    return {
        "total_gb": round(m.total / 2**30, 1),
        "used_gb": round(m.used / 2**30, 1),
        "avail_gb": round(m.available / 2**30, 1),
        "pct": round(float(m.percent), 1),
        "swap_total_gb": round(s.total / 2**30, 1),
        "swap_used_gb": round(s.used / 2**30, 1),
        "swap_pct": round(float(s.percent), 1),
    }


# ── GPU (nvidia-smi) ─────────────────────────────────────────────────────────
def _run(args: list[str]) -> str:
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=6)
        return out.stdout.strip()
    except Exception:                     # noqa: BLE001
        return ""


def _gpu() -> dict[str, Any]:
    q = ("--query-gpu=name,memory.used,memory.total,utilization.gpu,"
         "temperature.gpu,utilization.memory,power.draw,power.limit")
    raw = _run(["nvidia-smi", *q.split(), "--format=csv,noheader,nounits"])
    if not raw:
        return {"present": False}
    parts = [p.strip() for p in raw.splitlines()[0].split(",")]
    if len(parts) < 6:
        return {"present": False}
    used, total = float(parts[1]), float(parts[2])

    # which processes hold VRAM (ollama, kwin, browser …)
    procs: list[dict[str, Any]] = []
    praw = _run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory",
                 "--format=csv,noheader,nounits"])
    for line in praw.splitlines():
        cols = [c.strip() for c in line.split(",")]
        if len(cols) >= 3:
            name = cols[1].rsplit("/", 1)[-1]
            try:
                p = psutil.Process(int(cols[0])) if psutil else None
                cmd = " ".join(p.cmdline()[:3]) if p and p.cmdline() else name
            except Exception:             # noqa: BLE001
                cmd = name
            procs.append({"pid": int(cols[0]), "name": name, "cmd": cmd[:60],
                          "vram_mb": _mb(cols[2])})
    procs.sort(key=lambda x: -(x["vram_mb"] or 0))

    def f(x: str) -> float | None:
        try:
            return round(float(x), 1)
        except (ValueError, TypeError):
            return None

    power = f(parts[6]) if len(parts) > 6 else None
    # nvidia-smi on some laptops reports power.draw in mW for some samples
    # (seen 752.7 next to 11.2 W idle) — anything past ~150 W is a laptop GPU
    # max, so treat it as milliwatts and convert.
    if power is not None and power > 150:
        power = round(power / 1000, 1)

    return {
        "present": True,
        "name": parts[0],
        "vram_used_mb": int(used),
        "vram_total_mb": int(total),
        "vram_used_gb": round(used / 1024, 2),
        "vram_total_gb": round(total / 1024, 2),
        "vram_pct": round(used / total * 100, 1) if total else 0.0,
        "util_pct": f(parts[3]),
        "mem_util_pct": f(parts[5]),
        "temp_c": f(parts[4]),
        "power_w": power,
        "power_limit_w": f(parts[7]) if len(parts) > 7 else None,
        "processes": procs,
    }


def gpu() -> dict[str, Any]:
    """Public GPU snapshot (single source of truth for status + resources)."""
    return _gpu()


def _mb(s: str) -> float | None:
    try:
        return float(str(s).replace("MiB", "").replace("MB", "").strip())
    except (ValueError, TypeError):
        return None


# ── per-model footprint (Ollama) ─────────────────────────────────────────────
def _http_json(url: str, timeout: float = 4.0) -> Any:
    import urllib.request
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _post_json(url: str, payload: dict[str, Any], timeout: float = 90.0) -> Any:
    import urllib.request
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _gb(n: float | None) -> float | None:
    return round(n / 2**30, 2) if n else (0.0 if n == 0 else None)


def loaded_models() -> list[dict[str, Any]]:
    """Every model currently resident in RAM/VRAM, with its footprint."""
    try:
        data = _http_json(f"{OLLAMA_URL}/api/ps")
    except Exception:                     # noqa: BLE001
        return []
    out = []
    total_gpu_gb = 0.0
    g = _gpu()
    if g.get("present"):
        total_gpu_gb = float(g.get("vram_total_gb") or 0.0)
    for m in data.get("models", []):
        total = m.get("size") or 0
        vram = m.get("size_vram")
        vram = total if vram is None else vram
        ram = max(total - vram, 0)        # part that stayed in system RAM
        det = m.get("details", {}) or {}
        expires = str(m.get("expires_at") or "")
        pinned = expires.startswith("23")  # keep_alive -1 → year 2319
        vram_gb = _gb(vram)
        out.append({
            "name": m.get("name") or m.get("model"),
            "params": det.get("parameter_size"),
            "quant": det.get("quantization_level"),
            "family": det.get("family"),
            "context": m.get("context_length"),
            "size_gb": _gb(total),
            "vram_gb": vram_gb,
            "ram_gb": _gb(ram),
            "vram_pct": round(vram_gb / total_gpu_gb * 100, 1)
            if total_gpu_gb and vram_gb is not None else None,
            "pinned": pinned,
            "expires_at": expires,
            "on": True,
        })
    out.sort(key=lambda x: -(x["vram_gb"] or 0))
    return out


# ── keep-alive switch: pin (on) / unload (off) ───────────────────────────────
def set_keep(model: str, on: bool) -> dict[str, Any]:
    """Load + pin a model forever (keep_alive -1) or unload it (keep_alive 0).

    Returns the raw Ollama outcome so the caller can show `load` / `unload`.
    """
    if not model:
        return {"ok": False, "error": "no model given"}
    payload = {"model": model, "prompt": "", "keep_alive": -1 if on else 0}
    try:
        res = _post_json(f"{OLLAMA_URL}/api/generate", payload,
                         timeout=180 if on else 60)
        reason = res.get("done_reason") or ("load" if res.get("done") else "?")
        return {"ok": bool(res.get("done")), "model": model,
                "on": on, "reason": reason}
    except Exception as e:                 # noqa: BLE001
        return {"ok": False, "model": model, "on": on, "error": str(e)[:200]}


def restore_pins(models: list[str]) -> dict[str, Any]:
    """Re-apply the persisted keep-set after a tower restart (best effort)."""
    results = []
    for m in models:
        try:
            results.append(set_keep(m, True))
        except Exception:                 # noqa: BLE001
            pass
    ok = [r["model"] for r in results if r.get("ok")]
    return {"requested": len(models), "loaded": ok}


# ── combined snapshot for GET /api/resources ─────────────────────────────────
def snapshot() -> dict[str, Any]:
    """One call for the dashboard header: CPU, RAM, GPU, loaded models."""
    t0 = time.time()
    loaded = loaded_models()
    gpu = _gpu()
    used_vram = sum(m.get("vram_gb") or 0 for m in loaded)
    used_ram = sum(m.get("ram_gb") or 0 for m in loaded)
    return {
        "cpu": _cpu(),
        "mem": _mem(),
        "gpu": gpu,
        "models": loaded,
        "model_totals": {
            "loaded": len(loaded),
            "vram_gb": round(used_vram, 2),
            "ram_gb": round(used_ram, 2),
        },
        "ok": True,
        "elapsed_ms": round((time.time() - t0) * 1000, 1),
        "ts": time.time(),
    }
