"""Persisted tower state + a tiny thread-safe JSON store.

State holds only non-secret user choices (which model is default, agent model,
recent approvals). Secrets never come near this file (brain rule: assets stay
secret-free).
"""
from __future__ import annotations

import json
import threading
import time
from copy import deepcopy
from typing import Any

from .paths import STATE_FILE

# RLock, NOT Lock: decide_approval/add_approval take the lock and then call
# load(), which takes it again — a plain Lock self-deadlocks the event loop
# the moment the human clicks Approve (seen live: whole server wedged).
_lock = threading.RLock()

_DEFAULT: dict[str, Any] = {
    "default_model": "campus/penny:latest",     # local-first; user switches in UI
    "agent_model": "campus/penny:latest",       # the model that drives apps
    "deep_model": "qwen3.5:4b",                 # deep tier — hard reasoning on demand
    "fallback_to_cloud": True,
    "approvals_timeout_sec": 300,
    "approvals": [],                            # [{id, tool, args, task, status, ts}]
    "history": [],                              # recent chat summary entries (no secrets)
    "kept_on": [],                              # local models the user pinned ON (keep_alive -1)
}

# models ordered how the user last liked them (best local first)
LOCAL_PREFERENCE = [
    "campus/penny:latest",
    "qwen3:8b-local",
    "qwen2.5-coder:7b-ctx16k",
    "qwen-coder-7b-ctx8k:latest",
    "qwen2.5-coder:7b",
    "jan-v3.5-4b:latest",
    "qwen2.5vl:3b",
]


def load() -> dict[str, Any]:
    with _lock:
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                data = {}
        else:
            data = {}
        merged = deepcopy(_DEFAULT)
        merged.update({k: v for k, v in data.items() if k in _DEFAULT})
        return merged


def save(patch: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        current = deepcopy(_DEFAULT)
        if STATE_FILE.exists():
            try:
                current.update(json.loads(STATE_FILE.read_text()))
            except (json.JSONDecodeError, OSError):
                pass
        current.update(patch)
        tmp = STATE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(current, indent=2))
        tmp.replace(STATE_FILE)
        return current


# ── kept-on models (the per-model power switch) ──────────────────────────────
def kept_on() -> list[str]:
    """Names of local models the user chose to keep loaded (pinned in VRAM)."""
    return list(load().get("kept_on", []))


def set_kept(model: str, on: bool) -> list[str]:
    """Add/remove a model from the keep-set. Returns the new list."""
    state = load()
    keep = [m for m in state.get("kept_on", []) if m != model]
    if on and model not in keep:
        keep.append(model)
    save({"kept_on": keep})
    return keep


# ── approvals (the control-plane gate) ────────────────────────────────────────
_appr_seq = 0


def add_approval(tool: str, args: Any, task: str) -> dict[str, Any]:
    global _appr_seq
    state = load()
    with _lock:
        _appr_seq += 1
        entry = {
            "id": f"ap{_appr_seq}-{int(time.time())}",
            "tool": tool,
            "args": args,
            "task": task,
            "status": "pending",
            "ts": time.time(),
        }
        approvals = [a for a in state.get("approvals", []) if a.get("status") == "pending"]
        approvals.append(entry)
        state["approvals"] = approvals[-50:]
        tmp = STATE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=2))
        tmp.replace(STATE_FILE)
        return entry


def decide_approval(approval_id: str, approve: bool,
                    answer: str | None = None) -> dict[str, Any] | None:
    """approve=True (+optional free-form answer for ask_user) or approve=False."""
    with _lock:
        state = load()
        for a in state.get("approvals", []):
            if a["id"] == approval_id and a["status"] == "pending":
                a["status"] = "approved" if approve else "denied"
                a["decided"] = time.time()
                if answer:
                    a["answer"] = answer
                tmp = STATE_FILE.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(state, indent=2))
                tmp.replace(STATE_FILE)
                return a
    return None


def wait_approval(approval_id: str, timeout: float) -> str:
    """Poll until the human decides. Returns 'approved' | 'denied' | 'timeout'."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = load()
        for a in state.get("approvals", []):
            if a["id"] == approval_id:
                if a["status"] in ("approved", "denied"):
                    return a["status"]
        time.sleep(1.0)
    return "timeout"


def pending_approvals() -> list[dict[str, Any]]:
    """Pending AND still within the gate timeout — stale records (the human
    never saw them, e.g. an abandoned run) must not haunt the dashboard."""
    lim = float(load().get("approvals_timeout_sec", 300)) * 1.5
    now = time.time()
    return [a for a in load().get("approvals", [])
            if a.get("status") == "pending" and now - a.get("ts", now) < lim]


def get_approval(approval_id: str) -> dict[str, Any] | None:
    for a in load().get("approvals", []):
        if a["id"] == approval_id:
            return a
    return None
