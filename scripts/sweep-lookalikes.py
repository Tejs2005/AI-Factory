"""Sweep the tower browser's refusal logic against lookalike/homograph URLs.

Run:  python3 scripts/sweep-lookalikes.py   (from assets/ai-tower/)

Every MUST-REFUSE case must come back refused; every MUST-ALLOW case must
pass. Exit 1 on any miss, so it can run as a gate before browser changes.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tower.browser import _allowed  # noqa: E402

# the homoglyph 'а' below is CYRILLIC SMALL LETTER A, not 'a' — punycode and
# confusables are generated from these at runtime so the file stays honest.
CYR_A = "а"
CYR_E = "е"
CYR_O = "о"
CYR_P = "р"

MUST_REFUSE = [
    # plain payment/trading (regression guard — must keep firing)
    "https://paypal.com/login",
    "https://netbanking.hdfc.com",
    "https://coinbase.com/trade",
    "https://stripe.pay.example.com",
    # digit-leet lookalikes
    "https://paypa1.com",
    "https://raz0rpay.com",
    "https://krak3n.com",
    # cyrillic homoglyphs
    f"https://p{CYR_A}ypal.com",
    f"https://c{CYR_O}inb{CYR_A}se.com",
    f"https://stri{CYR_P}e.com",
    # punycode (the same homoglyph domains as the browser encodes them)
    "https://" + f"p{CYR_A}ypal.com".encode("idna").decode(),
    "https://" + f"c{CYR_O}inb{CYR_A}se.com".encode("idna").decode(),
    # non-ascii raw host, unencoded form
    f"https://p{CYR_A}ypal.com",
    # schemes
    "file:///etc/passwd",
    "chrome://settings",
    "about:blank",
    "view-source:http://example.com",
    # subdomain smuggling
    "https://paypal.evil-lookalike.example",
    "https://en.wikipedia.org/wiki/PayPal",
]
MUST_ALLOW = [
    # documented over-block: the raw-URL pass also matches the PATH, so even
    # an article *about* paypal is refused. Kept as a regression guard — a
    # loosening change (e.g. host-only matching) must fail this suite first.
    "https://github.com/Tejs2005",
    "https://duckduckgo.com",
    "https://news.ycombinator.com",
    "example.com",
    "https://en.wikipedia.org/wiki/Апостроф",  # cyrillic in the PATH is fine
]


def main() -> int:
    misses = 0
    print(f"{'case':<48} {'expect':<7} {'got':<8} verdict")
    print("─" * 90)
    for url in MUST_REFUSE:
        got = "refused" if _allowed(url) else "allowed"
        ok = got == "refused"
        misses += not ok
        print(f"{url[:48]:<48} refuse  {got:<8} {'✓' if ok else '✗ MISS'}")
    for url in MUST_ALLOW:
        got = "refused" if _allowed(url) else "allowed"
        ok = got == "allowed"
        misses += not ok
        print(f"{url[:48]:<48} allow   {got:<8} {'✓' if ok else '✗ MISS'}")
    print("─" * 90)
    print(f"{len(MUST_REFUSE) + len(MUST_ALLOW)} cases, {misses} misses")
    return 1 if misses else 0


if __name__ == "__main__":
    sys.exit(main())
