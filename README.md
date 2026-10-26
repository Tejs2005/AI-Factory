# 🏭 AI-Factory

**Your own AI factory on one laptop. Local-first. One gateway. A human gate on everything dangerous.**

One control plane that connects every local AI model and every app on the machine — a web
dashboard, a single OpenAI-compatible endpoint for anything to plug into, and an
approval-gated agent ("the Operator") that can actually drive the apps.

Built by [@Tejs2005](https://github.com/Tejs2005) on a 15 GB-RAM / 8 GB-VRAM laptop
because the cloud was expensive and the AI should live where the work lives.

---

## Why

Every AI tool wants to be the center of the universe — its own models, its own keys,
its own settings. AI-Factory flips it: **the laptop has ONE tower**, and everything
(Jan, Dyad, your scripts, your agent) points at one endpoint. Models are loaded from
one place. Keys live in one folder, masked everywhere. And when the AI wants to touch
the real world — launch an app, run a shell command, submit a form — it stops and
**asks a human**.

```
                       ┌─────────────────────────────┐
   Jan · Dyad · CLI ──▶│  127.0.0.1:7425/v1 (OpenAI) │
                       │                             │
   Dashboard ◀────────▶│  AI-FACTORY TOWER           │
   (any browser)       │                             │
                       │  router: local-first,       │──▶ Ollama (:11434)
   Operator agent ────▶│  cloud-last, tiered         │──▶ LocalAI (:8080)
   (tool loop +        │                             │──▶ speaches TTS/STT (:8000)
    approval gate)     │  apps registry · keys ·     │──▶ cloud fallback
                       │  skills/rules library       │    (groq, openrouter,
                       └─────────────────────────────┘    gemini, …)
```

## What's in the factory

| Piece | What it does |
|---|---|
| **Dashboard** | status pills, live VRAM/RAM/CPU meters, model cards with per-model power switches (load/unload from VRAM), chat, agent console, apps, logs |
| **Gateway** | `POST /v1/chat/completions` — OpenAI-compatible; local-first routing with per-provider fallback chain, dead providers benched with the reason inline |
| **Operator** | a tool-loop agent with ~20 tools (apps, web search, skills, browser, shell) — dangerous actions create an **approval card** in the dashboard and block until a human decides |
| **Model tiers** | a tiny on-device model picks tools fast, small models chat, a heavy "deep tier" handles hard reasoning — each tier sized to the hardware |
| **Apps registry** | `config/apps.json` — start/stop anything (AI engines, GIMP, OBS, containers) from the dashboard; agent launches go through the gate |
| **Keys** | drop key files in `~/.factory-secrets/`; health-checked, **only ever shown masked**, never in logs or the dashboard (enforced in code, not by convention) |
| **Speech** | Kokoro TTS + faster-whisper STT in one CPU container, OpenAI-audio-compatible routes |
| **Browser harness** | a headed Playwright browser the agent can drive — payment/trading domains refused outright, **including lookalikes** (punycode, Cyrillic homoglyphs, `paypa1.com`) |
| **Brain library** *(optional)* | point it at a folder of `SKILL.md` playbooks and numbered rules — the agent searches skills and carries the hard rules in its system prompt |

## Safety, in depth

The Operator is allowed to act — which is why three walls stand in front of it:

1. **Approval gate** — `launch_app`, `stop_app`, `run_shell`, non-GET `http_request`,
   form submissions: an approval card streams to the dashboard; the agent blocks until
   the human approves or denies (or the gate times out).
2. **DENY blocklist** — some things are refused **even after approval**: `rm -rf /`,
   `mkfs`, `dd of=/dev/*`, pipe-to-shell, `/etc/shadow`, shutdown, firewall gutting…
   Locked by a 56-case probe: `scripts/probe-deny.py` (exit 1 on any miss — run it
   after touching the regex).
3. **Browser refusals** — the agent's browser won't navigate to payment/trading
   domains, and won't be tricked by lookalikes either. Locked by
   `scripts/sweep-lookalikes.py` (24/24).

## Quickstart

```bash
git clone https://github.com/Tejs2005/AI-Factory
cd AI-Factory
pip install fastapi uvicorn httpx psutil

# local engines (any or all — the tower degrades gracefully)
ollama serve                       # :11434
# LocalAI / speaches / anything OpenAI-compatible — see config/apps.json

./bin/ai-tower up                  # dashboard: http://127.0.0.1:7425
./bin/ai-tower models              # what the tower can reach
./bin/ai-tower run "what's my GPU doing right now?"
```

Point anything OpenAI-speaking at it:

```
base_url = http://127.0.0.1:7425/v1
api_key  = tower
```

Cloud keys (optional): drop files named `groq.txt`, `openrouter.txt`, … into
`~/.factory-secrets/` — one key per file. The tower health-checks them and routes to
the alive ones only. Values are never displayed (masked forms only).

## Honest limits

- Built for one Linux laptop (the author's). Paths in `tower/paths.py` and
  `config/apps.json` are per-machine — edit them.
- The brain library is optional; without it those tabs are just empty.
- No multi-user anything. Loopback-only by design. The gate assumes **one human**.
- No telemetry, no accounts, no cloud dependency. That's the point.

## Stacks it stands on

[Ollama](https://ollama.com) · [LocalAI](https://localai.io) ·
[speaches](https://github.com/speaches-ai/speaches) (Kokoro + faster-whisper) ·
[Playwright](https://playwright.dev) · [FastAPI](https://fastapi.tiangolo.com)

## License

MIT — see [LICENSE](LICENSE).
