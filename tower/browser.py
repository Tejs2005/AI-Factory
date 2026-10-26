"""Browser harness — hands for the local models.

One persistent Playwright Chromium window the Operator drives through tools:
    browser_open    navigate (free)
    browser_read    page text + title + url (free)
    browser_click   click a selector or visible text (free — window is visible)
    browser_type    type into a field (free)
    browser_tabs    list open tabs (free)
    browser_back    history back (free)
    browser_shot    screenshot, saved under static/shots/ (free)
    browser_submit  submit a form / press Enter on it (GATED — server-side effect)

Safety lines drawn on purpose:
  * the browser runs HEADED — Tejas watches every step (that is the human loop)
  * payment/checkout domains are refused outright (see _BAD_DOMAINS) — and the
    hostname is checked AFTER folding homoglyphs/leet digits, so paypa1.com,
    Cyrillic раypal and their xn-- punycode forms hit the same wall (sweep:
    scripts/sweep-lookalikes.py)
  * punycode labels and non-ascii hostnames are refused outright — a host the
    agent cannot read is exactly what a lookalike looks like
  * file://, chrome:// and about: are refused
  * form submission — the one action that creates server-side effects — needs
    the same approval gate as launch/shell

Everything runs in the tower process with Playwright's async API. A failed
headed launch (no display) retries headless so the API stays usable.
"""
from __future__ import annotations

import os
import re
import time
import unicodedata
from typing import Any
from urllib.parse import unquote, urlsplit

from .paths import STATIC_DIR

# screenshots land in static/shots/ so the existing /static mount serves them
SHOTS_DIR = STATIC_DIR / "shots"

# never let a model navigate here without a human
_BAD_DOMAINS = re.compile(
    r"(paypal|stripe|razorpay|checkout|paytm|phonepe|gpay|google[- ]?pay|"
    r"\bbank\b|hdfc|icici|axisbank|sbi|chase|revolut|binance|coinbase|"
    r"wazirx|coindcx|bybit|kraken)", re.IGNORECASE)

_BAD_SCHEMES = ("file:", "chrome:", "about:", "view-source:", "devtools:")

# confusables NFKD will not fold on its own — Cyrillic/Greek twins and the
# classic leet digits, written as escapes so this file stays ASCII
_HOMOGLYPHS = str.maketrans({
    # Cyrillic
    "\u0430": "a", "\u0435": "e", "\u043e": "o", "\u0440": "p", "\u0441": "c",
    "\u0445": "x", "\u0443": "y", "\u0456": "i", "\u0455": "s", "\u0501": "d",
    "\u04bb": "h", "\u0458": "j", "\u049b": "k", "\u04cf": "l", "\u043c": "m",
    "\u0442": "t", "\u0432": "b", "\u043a": "k", "\u043d": "h",
    # Greek
    "\u03bd": "v", "\u03bf": "o", "\u03c1": "p", "\u03b1": "a", "\u03b5": "e",
    # leet digits
    "0": "o", "1": "l", "3": "e", "5": "s",
})


def _folded_host(url: str) -> str:
    """Hostname NFKD-normalised, homoglyphs and leet digits folded to their
    ascii twins, lowercased — what _BAD_DOMAINS should really match."""
    try:
        host = urlsplit(url).hostname or ""
    except ValueError:
        return ""
    host = unquote(host)
    host = unicodedata.normalize("NFKD", host)
    host = host.translate(_HOMOGLYPHS)
    host = "".join(ch for ch in host if not unicodedata.combining(ch))
    return host.lower()

_pw = None            # async_playwright handle
_browser = None
_ctx = None
_page = None
_headless = False
_last_url = ""


def _allowed(url: str) -> str | None:
    """-> error reason, or None when the url may be opened."""
    u = (url or "").strip()
    if not u:
        return "empty url"
    if not u.startswith(("http://", "https://")):
        if u.startswith(_BAD_SCHEMES):
            return f"scheme refused: {u.split(':')[0]}"
        u = "https://" + u                       # tolerate bare domains
    try:
        host = urlsplit(u).hostname or ""
    except ValueError:
        return "unparseable url"
    if not host:
        return "no host in url"
    # a hostname the agent cannot read is exactly what a lookalike looks like:
    # punycode labels and raw non-ascii hosts are refused outright
    if any(label.startswith("xn--") for label in host.split(".")):
        return f"punycode (IDN) domain refused — likely a lookalike ({host})"
    if not host.isascii():
        return f"non-ascii (homoglyph) domain refused — likely a lookalike ({host})"
    folded = _folded_host(u)
    if _BAD_DOMAINS.search(folded):
        return ("payment/trading domain refused (lookalike fold matched "
                f"{folded}) — ask Tejas in person")
    if _BAD_DOMAINS.search(u):
        return ("payment/trading domain refused — ask Tejas in person "
                f"({host})")
    return None


async def _ensure() -> Any:
    """Start (or reuse) the browser. Returns the active page."""
    global _pw, _browser, _ctx, _page, _headless
    if _page is not None and not _page.is_closed():
        return _page
    from playwright.async_api import async_playwright
    if _pw is None:
        _pw = await async_playwright().start()
    os.environ.setdefault("DISPLAY", ":0")
    # NB: no --ozone-platform flag — Chromium 156 fatals on "auto"
    # (FATAL: Invalid ozone platform → SIGTRAP) and picks Wayland by itself.
    args = ["--disable-blink-features=AutomationControlled",
            "--no-first-run", "--no-default-browser-check"]
    try:
        _browser = await _pw.chromium.launch(headless=_headless, args=args)
    except Exception:                            # noqa: BLE001 — no display → headless
        _headless = True
        _browser = await _pw.chromium.launch(headless=True, args=args)
    _ctx = await _browser.new_context(viewport={"width": 1440, "height": 900},
                                      locale="en-US")
    _ctx.set_default_timeout(20_000)
    _page = await _ctx.new_page()
    return _page


async def close() -> None:
    global _pw, _browser, _ctx, _page
    for obj in (_ctx, _browser):
        try:
            if obj:
                await obj.close()
        except Exception:                        # noqa: BLE001
            pass
    try:
        if _pw:
            await _pw.stop()
    except Exception:                            # noqa: BLE001
        pass
    _pw = _browser = _ctx = _page = None


async def _resolve(pg: Any, sel: str):
    """CSS selector first, then visible text / button name."""
    try:
        loc = pg.locator(sel)
        if await loc.count() > 0:
            return loc.first
    except Exception:                            # noqa: BLE001 — not a selector
        pass
    for loc in (pg.get_by_text(sel, exact=False),
                pg.get_by_role("button", name=sel),
                pg.get_by_role("link", name=sel),
                pg.get_by_placeholder(sel)):
        try:
            if await loc.count() > 0:
                return loc.first
        except Exception:                        # noqa: BLE001
            continue
    return None


# ── the tools the agent sees ─────────────────────────────────────────────────
async def open_url(url: str) -> dict[str, Any]:
    global _last_url
    bad = _allowed(url)
    if bad:
        return {"error": bad}
    t0 = time.time()
    try:
        pg = await _ensure()
        await pg.goto(url if url.startswith("http") else "https://" + url,
                      wait_until="domcontentloaded")
        try:
            await pg.wait_for_load_state("networkidle", timeout=6000)
        except Exception:                        # noqa: BLE001 — busy pages are fine
            pass
        _last_url = pg.url
        return {"ok": True, "url": pg.url, "title": await pg.title(),
                "ms": int((time.time() - t0) * 1000), "headless": _headless}
    except Exception as e:                       # noqa: BLE001
        return {"error": str(e)[:300]}


async def read_page(max_chars: int = 6000) -> dict[str, Any]:
    try:
        pg = await _ensure()
        text = await pg.locator("body").inner_text()
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        links = await pg.eval_on_selector_all(
            "a[href]", "els=>els.slice(0,40).map(e=>({t:(e.innerText||'').trim().slice(0,60),h:e.href}))")
        return {"url": pg.url, "title": await pg.title(),
                "text": text[:max_chars], "truncated": len(text) > max_chars,
                "links": [l for l in links if l.get("t")][:20]}
    except Exception as e:                       # noqa: BLE001
        return {"error": str(e)[:300]}


async def click(sel: str) -> dict[str, Any]:
    global _last_url
    try:
        pg = await _ensure()
        loc = await _resolve(pg, sel)
        if loc is None:
            return {"error": f"nothing matches {sel!r}",
                    "tip": "pass exact button/link text or a css selector"}
        label = ""
        try:
            label = (await loc.inner_text())[:60]
        except Exception:                        # noqa: BLE001 — e.g. svg nodes
            pass
        await loc.click(timeout=8000)
        try:
            await pg.wait_for_load_state("domcontentloaded", timeout=6000)
        except Exception:                        # noqa: BLE001
            pass
        _last_url = pg.url
        return {"ok": True, "clicked": label or sel, "url": pg.url,
                "title": await pg.title()}
    except Exception as e:                       # noqa: BLE001
        return {"error": str(e)[:300]}


async def type_text(sel: str, text: str, press_enter: bool = False) -> dict[str, Any]:
    if press_enter:
        return {"error": "press_enter is a form submission — use browser_submit"}
    try:
        pg = await _ensure()
        loc = await _resolve(pg, sel)
        if loc is None:
            return {"error": f"nothing matches {sel!r}"}
        await loc.fill(text, timeout=8000)
        return {"ok": True, "typed_into": sel, "chars": len(text)}
    except Exception as e:                       # noqa: BLE001
        return {"error": str(e)[:300]}


async def submit(sel: str = "") -> dict[str, Any]:
    """GATED caller-side. Submits a form or presses Enter in a field."""
    try:
        pg = await _ensure()
        if sel:
            loc = await _resolve(pg, sel)
            if loc is None:
                return {"error": f"nothing matches {sel!r}"}
            await loc.press("Enter", timeout=8000)
        else:
            await pg.keyboard.press("Enter")
        try:
            await pg.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:                        # noqa: BLE001
            pass
        bad = _allowed(pg.url)
        if bad:
            return {"error": "landed on a refused domain: " + bad}
        return {"ok": True, "url": pg.url, "title": await pg.title()}
    except Exception as e:                       # noqa: BLE001
        return {"error": str(e)[:300]}


async def tabs() -> dict[str, Any]:
    try:
        pg = await _ensure()
        out = []
        for i, p in enumerate(_ctx.pages):
            try:
                out.append({"i": i, "url": p.url, "title": await p.title(),
                            "active": p == pg})
            except Exception:                    # noqa: BLE001
                out.append({"i": i, "url": p.url, "title": "?"})
        return {"tabs": out, "headless": _headless}
    except Exception as e:                       # noqa: BLE001
        return {"error": str(e)[:300]}


async def back() -> dict[str, Any]:
    try:
        pg = await _ensure()
        await pg.go_back(timeout=8000)
        return {"ok": True, "url": pg.url, "title": await pg.title()}
    except Exception as e:                       # noqa: BLE001
        return {"error": str(e)[:300]}


async def shot(name: str = "") -> dict[str, Any]:
    """Screenshot → saved under logs/shots and served at /static/shots/."""
    try:
        pg = await _ensure()
        SHOTS_DIR.mkdir(parents=True, exist_ok=True)
        fn = SHOTS_DIR / f"{name or 'shot'}-{int(time.time())}.png"
        await pg.screenshot(path=str(fn), full_page=False)
        return {"ok": True, "file": f"/static/shots/{fn.name}",
                "url": pg.url, "size": fn.stat().st_size}
    except Exception as e:                       # noqa: BLE001
        return {"error": str(e)[:300]}


async def alive() -> dict[str, Any]:
    return {"running": _page is not None and not _page.is_closed(),
            "headless": _headless, "url": _last_url}
