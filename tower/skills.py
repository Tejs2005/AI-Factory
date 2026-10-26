"""Skills library — VRTX-BRAIN's 582 SKILL.md files exposed to the tower.

Location:  ~/VRTX-BRAIN/brain/skills/<category>/<skill>/SKILL.md
Format:    frontmatter (name, description) + markdown instructions

Two operations for the agent:
  search_skills(query)  which skills are relevant (name/category/description match)
  read_skill(name)      load the full instructions

Everything is indexed once into config/skills-index.json (no secrets, just
names + descriptions + paths) so search is instant and file scanning happens
once. `index()` re-reads the frontmatter of every skill (~580 small files).
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any

from .paths import BRAIN, CONFIG_DIR

SKILLS_DIR = BRAIN / "brain" / "skills"
INDEX_FILE = CONFIG_DIR / "skills-index.json"
READ_CAP = 24_000          # chars returned by read_skill()

_lock = threading.Lock()
_index: list[dict[str, Any]] | None = None
_built_at = 0.0
TTL = 600                  # reindex at most every 10 min

_FM = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


def _frontmatter(text: str) -> dict[str, str]:
    m = _FM.match(text)
    if not m:
        return {}
    out: dict[str, str] = {}
    key = None
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            key, _, val = line.partition(":")
            out[key.strip()] = val.strip()
        elif key:                       # continuation of a long description
            out[key] = (out[key] + " " + line.strip()).strip()
    return out


def build() -> list[dict[str, Any]]:
    """Scan every SKILL.md and return the index (also cached to disk)."""
    items: list[dict[str, Any]] = []
    if not SKILLS_DIR.exists():
        return items
    for md in sorted(SKILLS_DIR.glob("*/*/SKILL.md")):
        try:
            head = md.read_text(errors="replace")[:6000]
        except OSError:
            continue
        fm = _frontmatter(head)
        name = fm.get("name") or md.parent.name
        desc = fm.get("description", "")
        body = head[_FM.match(head).end():] if _FM.match(head) else head
        first_heading = ""
        for line in body.splitlines():
            if line.startswith("# "):
                first_heading = line[2:].strip()
                break
        items.append({
            "name": name,
            "category": md.parent.parent.name,
            "desc": desc,
            "title": first_heading or name,
            "path": str(md),
        })
    try:
        INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
        INDEX_FILE.write_text(json.dumps(items, ensure_ascii=False))
    except OSError:
        pass
    return items


def index(force: bool = False) -> list[dict[str, Any]]:
    global _index, _built_at
    with _lock:
        if _index is not None and not force and time.time() - _built_at < TTL:
            return _index
        if not force and INDEX_FILE.exists() and _index is None:
            try:
                _index = json.loads(INDEX_FILE.read_text())
                _built_at = time.time()
                # still rebuild in background-ish fashion below if stale file
                if time.time() - INDEX_FILE.stat().st_mtime < TTL:
                    return _index
            except (OSError, json.JSONDecodeError):
                pass
        _index = build()
        _built_at = time.time()
        return _index


def _tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9.+]+", s.lower()) if len(t) > 1]


def search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Keyword-ish scoring: skill name > category > description > title."""
    items = index()
    q = query.lower().strip()
    if not q:
        return []
    qtoks = _tokens(q)
    scored: list[tuple[float, dict[str, Any]]] = []
    for it in items:
        name, cat = it["name"].lower(), it["category"].lower()
        desc, title = it["desc"].lower(), it.get("title", "").lower()
        score = 0.0
        if q in name or q in title:
            score += 12
        if q in desc:
            score += 6
        for t in qtoks:
            if t in name:
                score += 5
            if t in cat.replace("-", " ") or t == cat:
                score += 3
            if t in title:
                score += 2
            if t in desc:
                score += 1
        if score:
            scored.append((score, it))
    scored.sort(key=lambda x: -x[0])
    out = []
    for s, it in scored[:limit]:
        out.append({**it, "score": round(s, 1),
                    "excerpt": (it["desc"][:220] + ("…" if len(it["desc"]) > 220 else ""))})
    return out


def get(name: str) -> dict[str, Any] | None:
    name = name.strip().lower()
    items = index()
    return next((i for i in items if i["name"].lower() == name), None)


def read(name: str) -> dict[str, Any]:
    it = get(name)
    if not it:
        near = [i["name"] for i in search(name, 5)]
        return {"error": f"no skill named {name!r}",
                "nearest": near}
    try:
        text = Path(it["path"]).read_text(errors="replace")
    except OSError as e:
        return {"error": str(e)}
    return {"name": it["name"], "category": it["category"],
            "desc": it["desc"], "content": text[:READ_CAP],
            "truncated": len(text) > READ_CAP,
            "path": it["path"]}


def stats() -> dict[str, Any]:
    items = index()
    cats: dict[str, int] = {}
    for i in items:
        cats[i["category"]] = cats.get(i["category"], 0) + 1
    return {"total": len(items), "categories": cats,
            "dir": str(SKILLS_DIR), "built_at": _built_at}
