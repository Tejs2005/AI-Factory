"""App registry — the tower's control surface over every local app.

Registry lives in config/apps.json (editable, no secrets in it).
kinds:
  service   — long-running server the tower can start/monitor (ports/urls)
  desktop   — GUI app launched detached (Jan, BrowserOS, GIMP, …)
  tool      — CLI the agent may invoke (whisper, …)
  connector — external platform APIs (Gmail/YouTube/Instagram): needs keys,
              status = configured | not-configured

Safety:
  * user clicks in the dashboard run directly
  * agent-driven launch/stop goes through the approval gate (see agent.py)
  * every launch is logged to logs/apps.log with timestamp + source
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .paths import APPS_FILE, LOGS_DIR

_log = LOGS_DIR / "apps.log"


def load_registry() -> list[dict[str, Any]]:
    if not APPS_FILE.exists():
        return []
    data = json.loads(APPS_FILE.read_text())
    if isinstance(data, dict):                       # {"apps": [...]} wrapper
        data = data.get("apps", [])
    return [a for a in data if isinstance(a, dict)]


def save_registry(entries: list[dict[str, Any]]) -> None:
    APPS_FILE.write_text(json.dumps(entries, indent=2, ensure_ascii=False))


def get(app_id: str) -> dict[str, Any] | None:
    return next((a for a in load_registry() if a["id"] == app_id), None)


def _log_line(msg: str) -> None:
    with _log.open("a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}\n")


def _port_open(host: str, port: int, timeout: float = 0.6) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def status(app: dict[str, Any]) -> str:
    """running | available | missing | not-configured | unknown"""
    check = app.get("check") or {}
    kind = app.get("kind", "desktop")

    if kind == "connector":
        return "not-configured" if not app.get("configured") else "available"

    if check.get("type") == "tcp":
        u = urlparse(check["target"]) if "://" in check["target"] else None
        if u:
            host, port = u.hostname or "127.0.0.1", u.port or 80
        else:
            host, _, p = check["target"].rpartition(":")
            host, port = (host or "127.0.0.1"), int(p)
        return "running" if _port_open(host, port) else "available"
    if check.get("type") == "exec-check":                     # pgrep -f
        r = subprocess.run(["pgrep", "-f", check["pattern"]], capture_output=True)
        return "running" if r.returncode == 0 else "available"

    if app.get("exec") or app.get("cmd"):
        exe = (app.get("exec") or app.get("cmd"))
        first = exe[0] if isinstance(exe, list) else exe.split()[0]
        if first.startswith("/") and not Path(first).exists():
            return "missing"
        if not first.startswith("/") and shutil.which(first) is None and "AppImage" not in exe:
            return "missing"
        return "available"
    return "unknown"


def all_status() -> list[dict[str, Any]]:
    out = []
    for app in load_registry():
        a = dict(app)
        a["status"] = status(app)
        a.pop("secrets", None)                       # never leak anything sensitive
        out.append(a)
    return out


def launch(app_id: str, source: str = "user") -> dict[str, Any]:
    app = get(app_id)
    if not app:
        return {"ok": False, "error": "unknown app"}
    if app.get("kind") == "service" and app.get("start"):
        # service start may be a shell string (LocalAI needs a specific cwd)
        cwd = app.get("cwd") or None
        log = (LOGS_DIR / f"{app_id}.out").open("a")
        subprocess.Popen(app["start"], shell=True, cwd=cwd, start_new_session=True,
                         stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        _log_line(f"launch service {app_id} source={source}")
        return {"ok": True, "started": app_id, "note": "service starting, may take a moment"}

    exe = app.get("exec")
    if not exe:
        return {"ok": False, "error": "app has no exec"}
    args = exe if isinstance(exe, list) else exe.split()
    if not args[0].startswith("/") and shutil.which(args[0]) is None:
        return {"ok": False, "error": f"{args[0]} not found on this machine"}

    env = {**__import__("os").environ, "DISPLAY": __import__("os").environ.get("DISPLAY", ":0")}
    log = (LOGS_DIR / f"{app_id}.out").open("a")
    subprocess.Popen(args, cwd=app.get("cwd") or None, start_new_session=True,
                     stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env)
    _log_line(f"launch {app_id} source={source}")
    return {"ok": True, "started": app_id}


def stop(app_id: str, source: str = "user") -> dict[str, Any]:
    app = get(app_id)
    if not app:
        return {"ok": False, "error": "unknown app"}
    pattern = app.get("stop_pattern")
    if not pattern:
        return {"ok": False, "error": "this app has no safe stop pattern"}
    r = subprocess.run(["pkill", "-f", pattern], capture_output=True)
    _log_line(f"stop {app_id} source={source} rc={r.returncode}")
    return {"ok": r.returncode == 0,
            "note": "stopped" if r.returncode == 0 else "no matching process"}


def recent_log(n: int = 120) -> list[str]:
    if not _log.exists():
        return []
    return _log.read_text(errors="replace").splitlines()[-n:]
