"""Read keys from the brain's locked secrets store.

Rules obeyed here (see secrets/README.md + rule 002):
  * values are read live from secrets/ — never copied into assets/ or config/
  * a value never leaves this module except as a masked form (mask())
  * nothing in here logs or prints key material
"""
from __future__ import annotations

import re
from pathlib import Path

from .paths import SECRETS_DIR

# file stem -> (provider id, extraction)  — "first" = first non-empty non-comment line
_KEY_PATTERNS = {
    "google-gemini": re.compile(r"^(AQ\.[A-Za-z0-9_\-\.]+|AIza[\w\-]{30,})$"),
    "openrouter": re.compile(r"^sk-or-[\w\-]+$"),
    "groq": re.compile(r"^gsk_[\w\-]+$"),
    "anyapi": re.compile(r"^sk-[\w\-]{8,}$"),
    "cohere": re.compile(r"^(cohere_[\w\-]+|[a-z0-9]{32,})$"),
    "nscale cloud": re.compile(r"^vck_[\w\-]+$"),
    "cloudflare": re.compile(r"^cfut_[\w\-]+$"),
}
# lines like `account_id=…` are fields, never keys
_FIELD_LINE = re.compile(r"^[A-Za-z0-9_\-]+=")
_HEX32 = re.compile(r"^[0-9a-f]{32}$", re.I)


def _read_lines(name: str) -> list[str]:
    p = SECRETS_DIR / name
    if not p.exists():
        return []
    return p.read_text(errors="replace").splitlines()


def extract_key(filename: str) -> str | None:
    """Pull the key token out of a secret file (files carry notes/urls too)."""
    pat = _KEY_PATTERNS.get(Path(filename).stem)      # callers pass "groq.txt"
    lines = [ln.strip() for ln in _read_lines(filename)]
    for ln in lines:
        if not ln or ln.startswith("#") or _FIELD_LINE.match(ln):
            continue
        if pat and pat.match(ln):
            return ln
    # no pattern match: fall back to first plausible token (skip `key=value` fields)
    for ln in lines:
        if ln and not ln.startswith(("#", "http")) and len(ln) >= 16 \
                and not _FIELD_LINE.match(ln):
            return ln
    return None


def account_id_of(filename: str) -> str | None:
    """32-hex account id for provider urls (Cloudflare style).

    Accepts an explicit `account_id=…` line, or a bare 32-hex line in the file.
    Never returns key material — only the account id (not a secret by itself).
    """
    for ln in _read_lines(filename):
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        if ln.lower().startswith("account_id"):
            _, _, v = ln.partition("=")
            v = v.strip().split()[0] if v.strip() else ""
            if _HEX32.match(v or ""):
                return v.lower()
        elif _HEX32.match(ln):
            return ln.lower()
    return None


def cohere_tokens() -> list[str]:
    """Cohere files carry two tokens (v1 + v2 era)."""
    out = []
    for ln in _read_lines("cohere"):
        ln = ln.strip()
        if ln and not ln.startswith("#") and len(ln) >= 30 and not ln.startswith("http"):
            out.append(ln)
    return out


def endpoint_of(filename: str) -> str | None:
    for ln in _read_lines(filename):
        ln = ln.strip()
        if ln.startswith("http") and "/v1" in ln:
            return ln.rstrip("/")
    return None


def mask(value: str) -> str:
    """Safe display form: head...tail. Never the value."""
    if not value:
        return ""
    if len(value) <= 10:
        return "•" * len(value)
    return f"{value[:5]}…{value[-4:]}"


def get(filename: str) -> str | None:
    return extract_key(filename)
