"""Rules — VRTX-BRAIN's 21 numbered rules exposed to the tower's Operator.

Location: ~/VRTX-BRAIN/rules/NNN-name/SKILL.md
Format:   YAML-ish frontmatter (kind, statement, gate_mode, lifecycle,
          violation_signal, affects) + the prose rule

Why the tower loads them:
  * the Operator's SYSTEM_PROMPT gets the hard-gate statements up front, so a
    local model cannot claim it never saw them
  * `list_rules` / `read_rule` give it the full text on demand
  * Rule 011 matters here: Tejas's direct instruction outranks every rule, and
    a bypass is recorded in rules/rule-breaks/

Rule 002 is enforced in code already: secrets are only ever *masked* (see
tower/secrets.py) — key values never reach the dashboard, logs or chat.
"""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import Any

from .paths import BRAIN

RULES_DIR = BRAIN / "rules"
READ_CAP = 20_000

_FM = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
_lock = threading.Lock()
_rules: list[dict[str, Any]] | None = None
_built_at = 0.0
TTL = 600


def _frontmatter(text: str) -> dict[str, Any]:
    m = _FM.match(text)
    if not m:
        return {}
    out: dict[str, Any] = {}
    key = None
    for line in m.group(1).splitlines():
        if line.startswith((" ", "\t")) and key and key == "violation_signal":
            out[key] = (str(out.get(key, "")) + " " + line.strip()).strip()
            continue
        if ":" in line and not line.startswith((" ", "\t")):
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip()
            if val.startswith("[") and val.endswith("]"):     # simple list
                val = [x.strip().strip('"\'') for x in val[1:-1].split(",")
                       if x.strip()]
            out[key] = val
        elif key:
            out[key] = (str(out.get(key, "")) + " " + line.strip()).strip()
    return out


def index(force: bool = False) -> list[dict[str, Any]]:
    global _rules, _built_at
    with _lock:
        if _rules is not None and not force and time.time() - _built_at < TTL:
            return _rules
        out: list[dict[str, Any]] = []
        if RULES_DIR.exists():
            for md in sorted(RULES_DIR.glob("*/SKILL.md")):
                try:
                    text = md.read_text(errors="replace")
                except OSError:
                    continue
                fm = _frontmatter(text)
                m = _FM.match(text)
                body = text[m.end():] if m else text
                title = ""
                for line in body.splitlines():
                    if line.startswith("# "):
                        title = line[2:].strip()
                        break
                num = md.parent.name.split("-")[0]
                out.append({
                    "num": num,
                    "id": md.parent.name,
                    "title": title or md.parent.name,
                    "kind": fm.get("kind", ""),
                    "statement": fm.get("statement", ""),
                    "gate_mode": fm.get("gate_mode", ""),
                    "lifecycle": fm.get("lifecycle", ""),
                    "affects": fm.get("affects", []),
                    "violation_signal": fm.get("violation_signal", []),
                    "path": str(md),
                })
        _rules, _built_at = out, time.time()
        return out


def list_rules(hard_only: bool = False) -> list[dict[str, Any]]:
    rules = index()
    if hard_only:
        rules = [r for r in rules if r["gate_mode"] == "hard"]
    return [{k: r[k] for k in ("num", "id", "title", "kind", "statement",
                               "gate_mode", "lifecycle")} for r in rules]


def get(num_or_id: str) -> dict[str, Any] | None:
    q = str(num_or_id).strip().lower()
    rules = index()
    return next((r for r in rules
                 if r["id"].lower() == q or r["num"] == q
                 or r["num"].lstrip("0") == q.lstrip("0")), None)


def read(num_or_id: str) -> dict[str, Any]:
    r = get(num_or_id)
    if not r:
        near = [x["id"] for x in index() if
                any(t in x["id"] for t in str(num_or_id).lower().split("-"))][:5]
        return {"error": f"no rule {num_or_id!r}", "nearest": near}
    try:
        text = Path(r["path"]).read_text(errors="replace")
    except OSError as e:
        return {"error": str(e)}
    return {**{k: r[k] for k in ("num", "id", "title", "kind", "statement",
                                 "gate_mode", "lifecycle")},
            "content": text[:READ_CAP], "truncated": len(text) > READ_CAP,
            "path": r["path"]}


def hard_statements() -> list[str]:
    """The compact constitution for the agent's system prompt."""
    return [f"Rule {r['num']}: {r['statement'].rstrip('.')}."
            for r in index() if r["gate_mode"] == "hard" and r["statement"]]


def warn_statements() -> list[str]:
    return [f"Rule {r['num']} ({r['gate_mode']}): {r['statement'].rstrip('.')}."
            for r in index() if r["gate_mode"] != "hard" and r["statement"]]


def stats() -> dict[str, Any]:
    rules = index()
    return {"total": len(rules),
            "hard": sum(1 for r in rules if r["gate_mode"] == "hard"),
            "warn": sum(1 for r in rules if r["gate_mode"] == "warn"),
            "active": sum(1 for r in rules if r["lifecycle"] == "active"),
            "dir": str(RULES_DIR)}
