"""The Operator — one or two local models driving every registered app.

Two engines:
  chat   classic tool loop through the tower router (penny / qwen / cloud)
  needle Needle 3 picks tools fast on-device (~0.5 s), then the chat model
         writes the final answer from the executed results

Gate (rule of the house): launch/stop/shell/non-GET calls create an approval
the human decides in the dashboard. The agent BLOCKS until decided (or times
out) and is told plainly whether it was approved or denied.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, AsyncIterator
from urllib.parse import unquote

import httpx

from . import apps as apps_mod
from . import router
from . import rules as rules_mod
from . import state
from .paths import CONFIG_DIR

NEEDLE_BASE = "http://127.0.0.1:8088"
NEEDLE_TOOLS_FILE = CONFIG_DIR / "needle-tools.json"
MAX_TURNS = 10

# ── tool schemas (shared by chat loop AND needle) ────────────────────────────
TOOLS: list[dict[str, Any]] = [
    {"name": "list_apps",
     "description": "List every app registered in the tower with its status (running/available).",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "app_status",
     "description": "Get status and details of one registered app.",
     "parameters": {"type": "object",
                    "properties": {"app_id": {"type": "string"}},
                    "required": ["app_id"]}},
    {"name": "tower_status",
     "description": "Health of all AI engines and cloud keys: ollama, localai, needle, providers.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "search_web",
     "description": "Search the web (DuckDuckGo) and get top results with titles and URLs.",
     "parameters": {"type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"]}},
    {"name": "search_skills",
     "description": "Search the skills library (how-to playbooks: dev, game-dev, "
                    "3D/CAD, security, media, business, writing...). Use before doing any "
                    "specialized task to find an existing playbook.",
     "parameters": {"type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"]}},
    {"name": "read_skill",
     "description": "Load the full instructions of a skill by its name (from search_skills). "
                    "Returns the SKILL.md playbook.",
     "parameters": {"type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"]}},
    {"name": "list_rules",
     "description": "List the brain rules (the constitution you operate under): "
                    "id, kind, gate_mode and one-line statement. hard = must obey.",
     "parameters": {"type": "object",
                    "properties": {"hard_only": {"type": "boolean"}}}},
    {"name": "read_rule",
     "description": "Read one brain rule in full by number or id (e.g. '2' or '002-secrets').",
     "parameters": {"type": "object",
                    "properties": {"rule": {"type": "string"}},
                    "required": ["rule"]}},
    {"name": "http_get",
     "description": "Fetch a URL with GET and return text (truncated). Read-only.",
     "parameters": {"type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"]}},
    {"name": "http_request",
     "description": "Send an HTTP request (method, url, optional json body) to an app's API. Non-GET needs approval.",
     "parameters": {"type": "object",
                    "properties": {"method": {"type": "string"},
                                   "url": {"type": "string"},
                                   "body": {"type": "string"}},
                    "required": ["method", "url"]}},
    {"name": "launch_app",
     "description": "Start a registered app (jan, browseros, gimp, obs, audacity, localai, needle...). Needs human approval.",
     "parameters": {"type": "object",
                    "properties": {"app_id": {"type": "string"}},
                    "required": ["app_id"]}},
    {"name": "stop_app",
     "description": "Stop a running registered app. Needs human approval.",
     "parameters": {"type": "object",
                    "properties": {"app_id": {"type": "string"}},
                    "required": ["app_id"]}},
    {"name": "run_shell",
     "description": "Run a shell command on the laptop. Needs human approval. Prefer other tools first.",
     "parameters": {"type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"]}},
    {"name": "ask_user",
     "description": "Ask the human a clarifying question. The answer arrives as tool output.",
     "parameters": {"type": "object",
                    "properties": {"question": {"type": "string"}},
                    "required": ["question"]}},
    {"name": "browser_open",
     "description": "Open a URL in the tower's browser (headed — the human watches). "
                    "Returns the final url, title and load time. Payment/trading sites refused.",
     "parameters": {"type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"]}},
    {"name": "browser_read",
     "description": "Read the current page: plain text, title, url and top links. "
                    "Call after browser_open.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "browser_click",
     "description": "Click a link or button on the current page by css selector OR its "
                    "visible text (e.g. 'Next' or '#submit').",
     "parameters": {"type": "object",
                    "properties": {"target": {"type": "string"}},
                    "required": ["target"]}},
    {"name": "browser_type",
     "description": "Type text into a field (selector or placeholder text). Does NOT submit.",
     "parameters": {"type": "object",
                    "properties": {"target": {"type": "string"},
                                   "text": {"type": "string"}},
                    "required": ["target", "text"]}},
    {"name": "browser_back",
     "description": "Go back in browser history.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "browser_shot",
     "description": "Screenshot the current page. Returns a /static/shots/… url to show the human.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "browser_submit",
     "description": "Submit the form currently focused (press Enter). Creates a server-side "
                    "effect — needs human approval.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "browser_tabs",
     "description": "List the browser's open tabs with their urls.",
     "parameters": {"type": "object", "properties": {}}},
]

GATED = {"launch_app", "stop_app", "run_shell", "http_request", "browser_submit"}
FREE_BROWSER = {"browser_open", "browser_read", "browser_click", "browser_type",
                "browser_back", "browser_shot"}

# defence in depth — never run these, even after an approval.
# Broad on purpose: it must catch variations, not just the textbook form.
# Lessons from the probe suite (2026-10-26):
#   * `\b` after a bare `/` never matches (no word char follows) — that leaked
#     `rm -rf /`. Targets must be matched on separator classes instead.
#   * rm: recursive flag AND dangerous target. Bare "/", "*", "--", "~",
#     $HOME and top-level system dirs are auto-denied; deeper user paths
#     (rm -rf /home/user/x) fall through to the HUMAN gate, not here.
#   * 2026-10-27 probe (scripts/probe-deny.py): `dd bs=1M of=/dev/…` slipped
#     past `\S*` (option arg has a space); `sudo passwd root` missed because
#     `\ssudo\s` needs a char before "sudo"; `shutdown --version` and deep
#     rm targets were over-blocked. All four fixed, suite green.
DENY_RE = re.compile(
    r"("
    # rm: recursive flag + dangerous target ("/*" needs its own arm: a bare
    # "/" arm consumes "/" and then "*" breaks the \s|$ terminator)
    r"(?:^|\s)rm\s+-\S*\s+(?:\*|--|\$HOME|~|/\*|/)(?:\s|['\"]|$)"
    r"|(?:^|\s)rm\s+-\S*\s+/(?:boot|etc|usr|var|bin|sbin|lib|opt|root"
    r"|proc|sys|dev|home)(?:\s|['\"]|$)"
    r"|(?:bash|sh|zsh|dash|ash)\b[^\n]{0,300}?rm\s+-\S*\s+(?:\*|--|\$HOME|~|/\*|/)"
    r"|mkfs|fdisk|parted\b|wipefs|dd\b[^|;&]*?(?:if|of)=/dev/|:\(\)\s*\{"
    r"|>\s*/dev/sd|>\s*/dev/nvme"
    r"|shutdown\b(?!\s*--)(?:\s|$)|reboot|poweroff|halt\b"
    r"|chmod\s+(?:-\S+\s+)*777\s+/etc|chmod\s+-R\s+777\s+/|chown\s+-R\b.*\s/"
    r"|/etc/(?:passwd|shadow|sudoers|fstab)"
    r"|mv\s+\S+\s+/etc/|>\s*/etc/(?:passwd|shadow|sudoers|fstab)"
    r"|curl[^|]*\|\s*sh|wget[^|]*\|\s*sh|curl[^|]*\|\s*bash|wget[^|]*\|\s*bash"
    r"|systemctl\s+(?:stop|disable|mask)\s+\S*(?:firewalld|firewall|ufw|apparmor"
    r"|selinux|nftables|iptables)\S*|ufw\s+disable"
    r"|(?:(?:^|[;&|])\s*(?:sudo\s+)?|\s+sudo\s+)passwd\s"
    r"|find\s[^|;&]*\s-delete\b|history\s+-c"
    r"|userdel|groupdel|crontab\s+-r|kill\s+-9\s+1\b|killall\s+-9"
    r"|mount\s+-o\s+remount|swapoff|sysctl\s+-w\s+kernel"
    r")",
    re.IGNORECASE)


def _constitution() -> str:
    """Hard brain rules baked into the system prompt — a small local model
    cannot claim it never saw them. Warn-level rules stay available via
    list_rules/read_rule so the prompt does not bloat."""
    try:
        hard = rules_mod.hard_statements()
    except Exception:  # noqa: BLE001
        return ""
    if not hard:
        return ""
    return ("\n\nBRAIN RULES (hard gate — always obey; full text: read_rule):\n"
            + "\n".join(f"- {s}" for s in hard)
            + "\n- Rule 011: Tejas's direct instruction outranks any rule; "
              "record the bypass in rules/rule-breaks/.")


SYSTEM_PROMPT = (
    "You are the AI Tower Operator on Tejas's Linux laptop. You control registered "
    "apps through your tools. Be direct and practical: gather facts first (status, "
    "web search), then act. Sensitive actions need human approval — say so briefly "
    "and wait; never claim something is done when it is only planned. When you have "
    "everything, answer with the result, not the process. "
    "Before a specialised task, check search_skills for an existing playbook; "
    "use list_rules/read_rule when unsure what the brain allows."
) + _constitution()


def write_needle_tools() -> None:
    # Needle gets the full toolbox now: browser_* (free) + gated tools +
    # ask_user (the needle loop routes it through _ask, same as chat).
    NEEDLE_TOOLS_FILE.write_text(json.dumps(TOOLS, indent=1))


# ── read-only helpers ────────────────────────────────────────────────────────
async def _search_web(query: str, limit: int = 6) -> list[dict[str, str]]:
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as c:
        r = await c.post("https://html.duckduckgo.com/html/",
                         data={"q": query},
                         headers={"User-Agent": "Mozilla/5.0 (AITower/1.0)"})
        r.raise_for_status()
        html = r.text
    out = []
    for m in re.finditer(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        url, title = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if "duckduckgo.com/l/" in url:
            q = re.search(r"uddg=([^&]+)", url)
            if q:
                url = unquote(q.group(1))
        out.append({"title": title, "url": url})
        if len(out) >= limit:
            break
    return out


async def _http_get(url: str, max_chars: int = 4000) -> dict[str, Any]:
    if not url.startswith(("http://127.0.0.1", "http://localhost", "https://")):
        return {"error": "only http(s) urls"}
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as c:
        r = await c.get(url, headers={"User-Agent": "Mozilla/5.0 (AITower/1.0)"})
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", r.text, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
    return {"status": r.status_code, "text": text[:max_chars]}


async def _run_shell(cmd: str) -> dict[str, Any]:
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
    except asyncio.TimeoutError:
        proc.kill()
        return {"error": "timed out after 60s"}
    return {"exit": proc.returncode, "output": out.decode(errors="replace")[:6000]}


def _needle_alive() -> bool:
    import socket
    try:
        with socket.create_connection(("127.0.0.1", 8088), timeout=1.5):
            return True
    except OSError:
        return False


# ── tool execution ───────────────────────────────────────────────────────────
async def _exec_free(name: str, args: dict[str, Any]) -> Any:
    if name == "list_apps":
        return apps_mod.all_status()
    if name == "app_status":
        return apps_mod.get(args.get("app_id", "")) or {"error": "unknown app"}
    if name == "tower_status":
        from . import providers
        h = providers.check_all()
        return {"engines": {"ollama": h["local"]["ollama"].get("alive"),
                            "localai": h["local"]["localai"].get("alive"),
                            "needle": _needle_alive()},
                "ollama_models": h["local"]["ollama"].get("models", []),
                "cloud": [{"id": c["id"], "alive": c.get("alive"),
                           "error": c.get("last_error")} for c in h["cloud"]]}
    if name == "search_web":
        try:
            return await _search_web(args.get("query", ""))
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)[:200]}
    if name == "http_get":
        try:
            return await _http_get(args.get("url", ""))
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)[:200]}
    if name == "search_skills":
        from . import skills as skills_mod
        try:
            return await asyncio.to_thread(skills_mod.search,
                                           args.get("query", ""), 8)
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)[:200]}
    if name == "read_skill":
        from . import skills as skills_mod
        try:
            return await asyncio.to_thread(skills_mod.read, args.get("name", ""))
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)[:200]}
    if name == "list_rules":
        hard = bool(args.get("hard_only"))
        try:
            return await asyncio.to_thread(rules_mod.list_rules, hard)
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)[:200]}
    if name == "read_rule":
        try:
            return await asyncio.to_thread(rules_mod.read, args.get("rule", ""))
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)[:200]}
    if name.startswith("browser_"):
        from . import browser as br
        try:
            if name == "browser_open":
                return await br.open_url(args.get("url", ""))
            if name == "browser_read":
                return await br.read_page()
            if name == "browser_click":
                return await br.click(args.get("target", ""))
            if name == "browser_type":
                return await br.type_text(args.get("target", ""),
                                          args.get("text", ""))
            if name == "browser_back":
                return await br.back()
            if name == "browser_shot":
                return await br.shot()
            if name == "browser_tabs":
                return await br.tabs()
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)[:300]}
        return {"error": f"unknown browser tool {name}"}
    if name == "ask_user":
        # callers must route ask_user through _ask() so the question is
        # streamed to the dashboard while we block for the answer
        return {"error": "ask_user must be routed through _ask()"}
    return {"error": f"unknown tool {name}"}


async def _exec_gated(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Run AFTER the human approved (wait happens in the caller so events flow)."""
    if name == "launch_app":
        return apps_mod.launch(args.get("app_id", ""), source="agent")
    if name == "stop_app":
        return apps_mod.stop(args.get("app_id", ""), source="agent")
    if name == "run_shell":
        cmd = args.get("command", "")
        if DENY_RE.search(cmd):
            return {"denied": True, "reason": "blocked by safety rule"}
        return await _run_shell(cmd)
    if name == "http_request":
        method = str(args.get("method", "GET")).upper()
        if method == "GET":
            return await _http_get(args.get("url", ""))
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as c:
            r = await c.request(method, args["url"], content=args.get("body"))
            return {"status": r.status_code, "text": r.text[:4000]}
    if name == "browser_submit":
        from . import browser as br
        try:
            return await br.submit(args.get("target", ""))
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)[:300]}
    return {"error": f"unknown gated tool {name}"}


async def _gate(name: str, args: dict[str, Any],
                task: str) -> AsyncIterator[dict[str, Any]]:
    """Approval record → STREAM it → block for the human → execute.

    Async generator on purpose: approval_pending must reach the dashboard
    BEFORE we block on the decision, otherwise the human never sees the box
    (that was the original deadlock: event delivered only after the wait).
    Final event carries `payload` = the actual tool result for the caller.
    """
    a = state.add_approval(name, args, task)
    yield {"type": "approval_pending", "approval": a}
    verdict = await asyncio.to_thread(
        state.wait_approval, a["id"],
        float(state.load().get("approvals_timeout_sec", 300)))
    if verdict != "approved":
        res: dict[str, Any] = {"denied": True, "reason": verdict,
                               "note": "the human did not approve this action"}
    else:
        res = await _exec_gated(name, args)
    yield {"type": "approval_result", "approval": a["id"],
           "status": verdict,
           "result": "executed" if verdict == "approved" else verdict,
           "payload": res}


async def _ask(args: dict[str, Any], task: str) -> AsyncIterator[dict[str, Any]]:
    """ask_user: stream the question as an approval card, block for the reply.

    The human answers with free text (stored as approval.answer) or just
    approves (= yes) / denies (= no). Same generator pattern as _gate.
    """
    question = args.get("question", "")
    a = state.add_approval("ask_user", args, question)
    yield {"type": "approval_pending", "approval": a}
    verdict = await asyncio.to_thread(
        state.wait_approval, a["id"],
        float(state.load().get("approvals_timeout_sec", 300)))
    rec = state.get_approval(a["id"]) or {}
    answer = rec.get("answer")
    if verdict == "approved":
        res: dict[str, Any] = {"answer": answer if answer else "yes"}
    elif verdict == "denied":
        res = {"answer": "no", "note": "the human declined to answer"}
    else:
        res = {"answer": "timeout", "note": "no answer within the gate timeout"}
    yield {"type": "approval_result", "approval": a["id"],
           "status": verdict, "result": res["answer"], "payload": res}


def _content_of(msg: dict[str, Any]) -> str:
    """Content as a plain string (some models return a parts list)."""
    c = msg.get("content") or ""
    if isinstance(c, list):
        c = "".join(p.get("text", "") for p in c if isinstance(p, dict))
    return str(c)


def _blocklisted(name: str, args: dict[str, Any]) -> bool:
    return name == "run_shell" and bool(DENY_RE.search(args.get("command", "")))


# ── the two agent modes ──────────────────────────────────────────────────────
async def run(task: str, mode: str = "auto", answer_model: str | None = None
              ) -> AsyncIterator[dict[str, Any]]:
    if mode in ("auto", "needle") and _needle_alive():
        async for ev in _run_needle(task, answer_model):
            yield ev
        return
    if mode == "needle":
        # needle not running — start it via the registry, one retry
        apps_mod.launch("needle", source="agent-service")
        for _ in range(20):
            await asyncio.sleep(1)
            if _needle_alive():
                async for ev in _run_needle(task, answer_model):
                    yield ev
                return
    async for ev in _run_chat(task, answer_model or state.load().get("agent_model")):
        yield ev


async def _run_chat(task: str, model: str | None) -> AsyncIterator[dict[str, Any]]:
    yield {"type": "start", "mode": "chat", "model": model}
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]
    for turn in range(1, MAX_TURNS + 1):
        resp = await router.chat_json({
            "model": model, "messages": messages,
            "tools": [{"type": "function", "function": t} for t in TOOLS],
            "temperature": 0.3,
        })
        if "error" in resp:
            yield {"type": "error", "error": resp["error"]}
            return
        yield {"type": "model_meta", **resp.get("_tower", {})}
        choice = (resp.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        tcs = msg.get("tool_calls") or []

        if not tcs:
            content = _content_of(msg)
            if not content.strip():
                # thinking models (penny) occasionally stop with an empty
                # content field — the answer is in `reasoning`. Retry once
                # with a plain nudge, then fall back to the reasoning itself.
                retry_msgs = messages + [
                    {"role": "user", "content": "Answer now, in plain words."}]
                r2 = await router.chat_json({
                    "model": model, "messages": retry_msgs,
                    "tools": [{"type": "function", "function": t} for t in TOOLS],
                    "temperature": 0.3})
                m2 = (r2.get("choices") or [{}])[0].get("message") or {}
                if not (m2.get("tool_calls") or []):
                    content = _content_of(m2)
                if not content.strip():
                    content = str(msg.get("reasoning") or m2.get("reasoning") or
                                  "(the model returned nothing)")
                else:
                    messages = retry_msgs           # keep the answered shape
            for i in range(0, len(content), 24):
                yield {"type": "token", "text": content[i:i + 24]}
                await asyncio.sleep(0.012)
            yield {"type": "done", "turns": turn, "final": content}
            return

        messages.append({k: v for k, v in msg.items()
                         if k in ("role", "content", "tool_calls")})
        for tc in tcs:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            gated = name in GATED and not _blocklisted(name, args)
            blocked = name in GATED and _blocklisted(name, args)
            yield {"type": "tool_call", "name": name, "args": args,
                   "gated": gated, "blocked": blocked}
            if blocked:
                result: Any = {"denied": True, "reason": "safety rule (always blocked)"}
            elif gated:
                result = None
                async for e in _gate(name, args, task):
                    yield e
                    if e.get("type") == "approval_result":
                        result = e.get("payload")
                if result is None:
                    result = {"error": "gate ended without a result"}
            elif name == "ask_user":
                result = None
                async for e in _ask(args, task):
                    yield e
                    if e.get("type") == "approval_result":
                        result = e.get("payload")
                if result is None:
                    result = {"error": "ask ended without a result"}
            else:
                result = await _exec_free(name, args)
            yield {"type": "tool_result", "name": name, "result": _trim(result)}
            messages.append({"role": "tool", "tool_call_id": tc.get("id", name),
                             "content": json.dumps(result, ensure_ascii=False,
                                                   default=str)[:8000]})
    yield {"type": "done", "turns": MAX_TURNS, "final": "(turn limit reached)"}


async def _run_needle(task: str, answer_model: str | None) -> AsyncIterator[dict[str, Any]]:
    st = state.load()
    fallback = answer_model or st.get("agent_model") or st.get("default_model")
    yield {"type": "start", "mode": "needle", "model": f"needle3 → {fallback}"}
    if not NEEDLE_TOOLS_FILE.exists():
        write_needle_tools()
    results: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    reasoning = ""
    try:
        async with httpx.AsyncClient(timeout=40.0) as c:
            await c.post(f"{NEEDLE_BASE}/reset")
            plan = await c.post(f"{NEEDLE_BASE}/complete", json={"input": task})
            pdata = plan.json()
        calls = pdata.get("function_calls") or []
        reasoning = pdata.get("reasoning") or ""
        yield {"type": "model_meta", "provider": "needle3",
               "confidence": pdata.get("confidence"),
               "reasoning": reasoning,
               "tps": pdata.get("decode_tps")}
    except Exception as e:  # noqa: BLE001
        yield {"type": "error", "error": f"needle unavailable: {str(e)[:120]}"}

    if not calls:
        # Needle won't handle it — hand the whole task to the chat loop
        yield {"type": "note", "text": reasoning or "no tool call; using chat model"}
        async for ev in _run_chat(task, fallback):
            if ev.get("type") != "start":
                yield ev
        return

    for call in calls:
        name, args = call.get("name", ""), call.get("arguments", {})
        gated = name in GATED and not _blocklisted(name, args)
        blocked = name in GATED and _blocklisted(name, args)
        yield {"type": "tool_call", "name": name, "args": args,
               "gated": gated, "blocked": blocked}
        if blocked:
            result: Any = {"denied": True, "reason": "safety rule"}
        elif gated:
            result = None
            async for e in _gate(name, args, task):
                yield e
                if e.get("type") == "approval_result":
                    result = e.get("payload")
            if result is None:
                result = {"error": "gate ended without a result"}
        elif name == "ask_user":
            result = None
            async for e in _ask(args, task):
                yield e
                if e.get("type") == "approval_result":
                    result = e.get("payload")
            if result is None:
                result = {"error": "ask ended without a result"}
        else:
            result = await _exec_free(name, args)
        yield {"type": "tool_result", "name": name, "result": _trim(result)}
        results.append({"tool": name, "args": args, "result": _trim(result)})

    synth = (f"Task given: {task}\n\nActions executed:\n"
             f"{json.dumps(results, indent=1, ensure_ascii=False, default=str)[:9000]}\n\n"
             "Write the final answer for Tejas. Mention any denied action honestly.")
    async for ev in _run_chat(synth, fallback):
        if ev.get("type") == "start":
            yield {"type": "model_meta", "provider": "answer-model", "model": fallback}
            continue
        yield ev


def _trim(v: Any, n: int = 4000) -> Any:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    if len(s) > n:
        return s[:n] + "…(truncated)"
    return v
