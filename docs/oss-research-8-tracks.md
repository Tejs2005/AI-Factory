# Open-Source Research — 8 Tracks for AI Tower

Date: **2026-10-26** · Stats verified live against the GitHub API unless marked *(via web)*.
Read alongside `docs/awesome-repos.md` (the earlier general catalog) — this file is the
**8-track deep dive**: gateways, small tool models, Ollama mgmt, HITL, free APIs,
connectors, GPU monitoring, media-gen servers.

Legend: **ADOPT** = run it as-is · **WIRE** = add as a component/API in the tower ·
**STEAL** = copy the pattern, not the code · **SKIP** = not worth it.

---

## Track 1 — Gateways & Dashboards

| # | Repo | ★ | License | Last push | One-liner | Verdict |
|---|---|---|---|---|---|---|
| 1 | [open-webui/open-webui](https://github.com/open-webui/open-webui) | 156,789 | BSD-3 (front) / custom (back) | 2026-10-26 | Self-hosted ChatGPT-style UI over Ollama + any OpenAI-compat API; RAG, tools, pipelines | **STEAL** (pipeline/routing code) |
| 2 | [BerriAI/litellm](https://github.com/BerriAI/litellm) | 62,050 | MIT | 2026-10-26 | Proxy/gateway: 100+ providers, one OpenAI-compat endpoint, budgets, fallbacks, key mgmt | **STEAL** (router + fallback logic) |
| 3 | [QuantumNous/new-api](https://github.com/QuantumNous/new-api) | 50,712 | AGPL-3.0 | 2026-10-25 | Chinese-fork of one-api: token/quota billing, channel mgmt, model mapping, pretty dashboard | **STEAL** (channel/ quota UI patterns) |
| 4 | [danny-avila/LibreChat](https://github.com/danny-avila/LibreChat) | 46,339 | MIT | 2026-10-26 | Multi-provider chat UI (OpenAI/Anthropic/Google/local), agents, MCP, Anthropic-compat endpoints | **ADOPT** (front door) |
| 5 | [Portkey-AI/gateway](https://github.com/Portkey-AI/gateway) | 13.2k | MIT | 2026-03 (Palo Alto acq.) | Fastify-based prod gateway: routing, retries, guardrails, tracing, fallbacks | **STEAL** (fallback/retry policy) |
| 6 | [getasterisk/astern](https://github.com/getasterisk/astern) | ~1.5k *(via web)* | MIT | 2026 | Minimal OpenAI-compat proxy + usage dashboard aimed at local setups | **SKIP** |
| 7 | [Bifrost](https://github.com/fleebeee/bifrost) | ~7.5k *(via web)* | MIT | 2026 | Go AI gateway, visually editable routing graphs | **SKIP** (Go, not Python) |
| 8 | [pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai) | ~14k *(via web)* | MIT | 2026 | Type-safe agent framework w/ model fallback, tracing, MCP — good pattern source | **STEAL** (type-safe tool defs) |

**Why they matter to the Tower:** the Tower already *is* a mini-LiteLLM (`tower/router.py`
walks a candidate chain). The valuable steals are:
- **LiteLLM's fallback + cooldown model** — how it benches a provider on 429/5xx, backs off
  with jitter, and records spend per key. Portkey does the same with circuit-breakers.
- **new-api's channel + model-mapping UI** — the exact "map `gpt-4o` → `penny:latest`"
  table you'd want in the dashboard's Models tab.
- **LibreChat's MCP + agent registry** — pattern for mounting external tool-servers.

---

## Track 2 — Small Tool-Calling Models (0.5B–4B)

For Needle 3's job (pick tools fast, on-device). Scores are BFCL V4 / TAU2 from leaderboards.

| # | Model | Size | BFCL / TAU2 | Notes | Verdict |
|---|---|---|---|---|---|
| 1 | **Qwen3.5-4B** | 4B dense | TAU2 **79.9** | Best-in-class dense small model; runs on ~8GB VRAM Q4 | **ADOPT** |
| 2 | **Qwen3.5-9B** | 9B | BFCL-V4 **66.1** | Fits 8GB quantized; strong general reasoning | **ADOPT** (if headroom) |
| 3 | **MadeAgents/Hammer2.1-1.5b** | 1.5B | BFCL **~82.0** (V3-style) | Purpose-built FC model, Qwen2.5-Coder base; repo **125★**, Apache-2.0, last push 2025-06 (models themselves still widely used) | **ADOPT** (candidate) |
| 4 | **Hammer2.1-7b** | 7B | BFCL-V4 **85.5** | Larger sibling, same series | **ADOPT** (if headroom) |
| 5 | **LiquidAI LFM2.5-1.2B** | 1.2B | ties #1 in an independent tool bench *(via web)* | Tiny, agentic-optimized, native function calling; HF repo not verified (API rate-limited) | **ADOPT** (candidate) |
| 6 | **Google FunctionGemma** | 270M | BFCL Simple **61.6** | Smallest serious FC model; needs a fine-tune + custom format | **WIRE** (long-term) |
| 7 | **IBM Granite 4.x 3B** | 3B | strong *(via web)* | Enterprise-friendly, Apache; praised in r/LocalLLaMA tool tests | **ADOPT** |
| 8 | **HuggingFace SmolLM3-3B** | 3B | decent *(via web)* | 128K context, strong for size | **SKIP** (Qwen3.5-4B is better) |
| 9 | **Qwen3-4B-Instruct-2507** | 4B | good | Previous-gen Qwen, still solid; repo `QwenLM/Qwen3` 27,682★, last push 2026-01 | **ADOPT** (fallback) |
| 10 | **Needle 3 (existing)** | 121M | — | Already serving on :8088 at ~600–860 tok/s | **keep** |

**Key insight (from benchmarks):** parameter count is a *weak* predictor of tool-calling
skill. A 121M–1.5B model purpose-trained for FC (Needle 3, Hammer2.1-1.5B, LFM2.5-1.2B)
can beat a 4B general model on raw tool-picking latency/accuracy. The real gap is
**multi-step, stateful** tool use — where the 4B+ models pull ahead. Recommend keeping
Needle 3 as the fast router and adding **Qwen3.5-4B** as the "deeper" tier.

---

## Track 3 — Ollama Management / Routing / VRAM Accounting

| # | Repo | ★ | License | Last push | What it does | Verdict |
|---|---|---|---|---|---|---|
| 1 | **Ollama native** `/api/ps` + `OLLAMA_NUM_PARALLEL` / `OLLAMA_MAX_LOADED_MODELS` / `OLLAMA_MAX_QUEUE` | — | MIT | current | The official way to see **which models are resident + their VRAM**, and to cap concurrency | **WIRE** (use directly) |
| 2 | [peva3/SmarterRouter](https://github.com/peva3/SmarterRouter) | 154 | MIT | 2026-05-10 | VRAM-aware router for Ollama / llama.cpp / OpenAI + semantic caching + model profiling | **STEAL** (VRAM-aware selection) |
| 3 | [aleibovici/ollama-gpu-calculator](https://github.com/aleibovici/ollama-gpu-calculator) | 73 | MIT | 2026-09-12 | Computes VRAM footprint for a given model/quant/context | **WIRE** (embed as a helper fn) |
| 4 | [NorskHelsenett/ollama-metrics](https://github.com/NorskHelsenett/ollama-metrics) | 42 | — | 2025-06-24 | Prometheus-metrics proxy in front of Ollama | **STEAL** (metrics shape) |
| 5 | [ollama-admin/ollama-admin](https://github.com/ollama-admin/ollama-admin) | 30 | — | 2026-08-06 | Admin panel + observability gateway for Ollama | **STEAL** (dashboard widgets) |
| 6 | [lasdem/ollama_admin_tools](https://github.com/lasdem/ollama_admin_tools) | 13 | MIT | 2026-08-27 | CLI helpers for Ollama admin | **SKIP** |
| 7 | **LiteLLM proxy** (again) | 62,050 | MIT | 2026-10-26 | Also does Ollama load-aware routing + spend tracking per model | **STEAL** |
| 8 | **Ollama's own docs** on `OLLAMA_NUM_PARALLEL`, KV-cache VRAM math | — | — | current | How to size context vs. batch for multi-model serving | **WIRE** (config guidance) |

**Wiring notes:**
- The Tower can call `GET http://localhost:11434/api/ps` to get, per running model:
  `name`, `size` (bytes on disk), `details.parameter_size`, `details.quantization_level`,
  `expires_at`. Combine with **nvitop** (Track 7) for true GPU-side VRAM.
- `aleibovici/ollama-gpu-calculator` is a tiny pure-function lib — drop-in for a
  "will this fit?" check before auto-loading a model.
- **No big maintained Ollama-manager exists.** The category is dominated by gateways
  (Track 1) + generic GPU monitors (Track 7). Building a thin VRAM-accounting layer on
  top of `/api/ps` + NVML is the right call.

---

## Track 4 — Human-in-the-Loop / Approval Patterns

| # | Repo | ★ | License | Last push | Pattern | Verdict |
|---|---|---|---|---|---|---|
| 1 | [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | 43,923 | MIT | 2026-10-26 | `interrupt()` → persist state → `Command(resume=...)` durable checkpoint pattern; approve/reject/edit with full audit trail | **STEAL** (the gold standard) |
| 2 | [langchain-ai/langchain](https://github.com/langchain-ai/langchain) | ~115k *(via web)* | MIT | 2026 | HITL middleware (`HumanApprovalMiddleware`) — policy hooks before tool execution | **STEAL** (middleware shape) |
| 3 | [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) | 91,878 | MIT | 2026-10-26 | `ConfirmationPolicy` = LOW / HIGH risk levels before shell/file actions | **STEAL** (risk-tiering) |
| 4 | [aaif-goose/goose](https://github.com/aaif-goose/goose) | 55,732 | Apache-2.0 | 2026-10-26 | (formerly Block's goose) — per-tool approval UI + recipe system; the closest product analog to the Operator | **STEAL** (approval UX) |
| 5 | [microsoft/autogen](https://github.com/microsoft/autogen) | 61,569 | CC-BY-4.0 | 2026-10-16 | `UserProxyAgent` human-input termination + `allowed_or_disallowed_terminations` | **STEAL** |
| 6 | [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | 60,116 | MIT | 2026-10-26 | Crew-level "step callback" + human input before task execution | **STEAL** |
| 7 | **Claude Code's own permission system** (in this harness) | — | — | current | Six modes (`default` / `acceptEdits` / `plan` / `bypassPermissions` / `dontAsk` / `auto`) + `canUseTool` callback + allow/deny/ask rules + per-session memory | **STEAL** (the richest reference) |

**Wiring note:** the Tower already has a hard gate + `DENY_RE` blocklist in
`tower/agent.py`. The upgrades to steal:
1. **Risk tiering** (OpenHands): tag every tool `LOW` / `MED` / `HIGH`; only `HIGH` blocks.
2. **Durable checkpoint** (LangGraph): persist the pending action to disk so an approval
   survives a server restart / page refresh.
3. **Mode switch** (Claude Code): a dashboard toggle `plan → normal → auto` that scopes
   which tools auto-run without asking.

---

## Track 5 — Free LLM API Providers (+ 5b: maintained free-API lists)

### 5b. Maintained lists (subscribe to these)

| # | Repo | ★ | License | Last push | Notes | Verdict |
|---|---|---|---|---|---|---|
| 1 | [mnfst/awesome-free-llm-apis](https://github.com/mnfst/awesome-free-llm-apis) | 11,311 | CC0 | 2026-10-25 | Tracks permanent free tiers + trial credits, notes deprecations | **ADOPT** (source of truth) |
| 2 | [open-free-llm-api/awesome-freellm-apis](https://github.com/open-free-llm-api/awesome-freellm-apis) | 4,737 | — | 2026-10-26 | Backs freellm.net, daily-refreshed | **ADOPT** |
| 3 | [nejib1/Free-LLM](https://github.com/nejib1/Free-LLM) | ~1k *(via web)* | — | 2026-10-14 | Directory of 34+ free APIs, flags no-card options | **ADOPT** |

### 5. Providers — verified 2026-10-26

| Provider | Free tier (verified) | Card? | Base URL | Verdict |
|---|---|---|---|---|
| **Google AI Studio (Gemini)** | Generous free tier, 1M ctx on some models *(via web)* | No | `generativelanguage.googleapis.com` | **ADOPT** (already in chain) |
| **Groq** | ~30 RPM, ~6–8K TPM, 1,000–14,400 RPD (numbers vary by model/region) | No | `api.groq.com` | **ADOPT** (already in chain) |
| **Cerebras** | 5 RPM / 30K TPM / 1M TPD per official docs; **conflicting** claims of no-card 1M/day | **Conflicting** — official pricing says card required for trial | `api.cerebras.ai` | **ADOPT** (test with card) |
| **OpenRouter** | `:free` model suffix, rate-limited | No | `openrouter.ai/api` | **ADOPT** (already in chain) |
| **Cloudflare Workers AI** | 10,000 Neurons/day, 60+ models, no card | No | `api.cloudflare.com/client/v4` | **WIRE** (add) |
| **Scaleway Generative APIs** | 1,000,000 tokens one-time free | No | `api.scaleway.com` | **WIRE** (add) |
| **HuggingFace Inference Providers** | ~100K monthly free credits; partners = DeepInfra, Baseten, Scaleway, Nscale (Nebius/SambaNova/Hyperbolic dropped) | No (PRO $2/mo for more) | `api-inference.huggingface.co` | **WIRE** (add) |
| **Mistral (Experiment tier)** | Free tier, uses your prompts | No | `api.mistral.ai` | **WIRE** (add, note data use) |
| **NVIDIA NIM** (`build.nvidia.com`) | Free rate-limited | No | `integrate.api.nvidia.com` | **WIRE** (already benched — slow) |
| **Together AI** | $1 free credit for new accounts | No | `api.together.xyz` | **WIRE** (trial) |
| ~~**GitHub Models**~~ | — | — | — | **SKIP — retired 2026-07-30** |
| ~~**SambaNova free tier**~~ | — | — | — | **SKIP — ended; now Developer Tier (pay + earn)** |

**Wiring note:** the Tower's chain is `groq → openrouter → gemini → nscale → anyapi → cohere`.
Add **Cerebras, Cloudflare Workers AI, HuggingFace Inference Providers, Scaleway, Mistral**
as candidates. Keep `mnfst/awesome-free-llm-apis` on a weekly cron to catch deprecations
(GitHub Models and SambaNova both died silently this year).

---

## Track 6 — Connectors (Gmail / YouTube / Instagram / Browser)

| # | Repo | ★ | License | Last push | What it does | Verdict |
|---|---|---|---|---|---|---|
| 1 | [browser-use/browser-use](https://github.com/browser-use/browser-use) | 119,169 | MIT | 2026-10-24 | Python lib that lets an LLM drive a real browser (Playwright-backed) | **ADOPT** (already in apps.json) |
| 2 | [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | 91,574 | — | 2026-10-25 | The official MCP server collection (reference impls for Gmail/Drive/etc.) | **WIRE** |
| 3 | [google/mcp](https://github.com/google/mcp) | 4,665 | Apache-2.0 | 2026-08-17 | Google's **official** MCP servers repo (Gmail, Drive, Calendar, Sheets…) — managed remote endpoints, OAuth 2.0 | **ADOPT** (the live Gmail path) |
| 4 | [googleapis/google-api-python-client](https://github.com/googleapis/google-api-python-client) | ~9.0k *(via web)* | Apache-2.0 | current | The official Gmail/YouTube/Drive Python client — the non-MCP fallback | **ADOPT** |
| 5 | [googleworkspace/cli](https://github.com/googleworkspace/cli) | ~31.9k *(via web)* | Apache-2.0 | current | `gws` CLI — one binary for Gmail/Drive/Calendar/Sheets; ideal for the Operator's `run_shell` | **ADOPT** |
| 6 | [ZubeidHendricks/youtube-mcp-server](https://github.com/ZubeidHendricks/youtube-mcp-server) | 589 | MIT | 2026-08-08 | MCP server for YouTube Data API v3 — video mgmt, Shorts creation | **ADOPT** |
| 7 | [pauling-ai/youtube-mcp-server](https://github.com/pauling-ai/youtube-mcp-server) | ~1k *(via web)* | — | 2026 | 40+ YouTube tools, needs Google OAuth | **ADOPT** (alt) |
| 8 | [GongRzhe/Gmail-MCP-Server](https://github.com/GongRzhe/Gmail-MCP-Server) | — | — | **ARCHIVED 2026-03** | Was popular; now dead | **SKIP** |
| 9 | [subzeroid/instagrapi](https://github.com/subzeroid/instagrapi) | ~6,600 | custom | 2026-08-27 | Instagram **Private API** — post, DM, story, scrape | **ADOPT** (risky, see below) |
| 10 | [mlouielu/Instaloader](https://github.com/instaloader/instaloader) | ~13.1k *(via web)* | GPL-2.0 | 2026-07 | Instagram **scraping/download** (read-only, more stable than instagrapi) | **ADOPT** (read side) |
| 11 | **Meta Graph API** (official) | — | — | current | The ToS-safe way to publish to Instagram/Facebook | **ADOPT** (publish side) |

**Key calls:**
- **Gmail:** GongRzhe's is dead; use **Google's official MCP server** (`google/mcp`) with
  OAuth 2.0, or the `google-api-python-client` + `gws` CLI.
- **Instagram:** the private-API route (instagrapi) risks account bans. Split it:
  **publish via Graph API**, **read/scrape via Instaloader**, DM automation via instagrapi
  only if you accept the risk.
- **YouTube:** two solid MCP options; the ZubeidHendricks one is simpler (API-key only
  for read ops).
- **Browser:** browser-use is the glue — already registered, just needs the key/OAuth.

---

## Track 7 — GPU Resource Monitoring

| # | Repo | ★ | License | Last push | What it does | Verdict |
|---|---|---|---|---|---|---|
| 1 | [XuehaiPan/nvitop](https://github.com/XuehaiPan/nvitop) | 7,226 | Apache-2.0 | **2026-10-26** | htop-style GPU monitor + **Python API** (`nvitop.api`, `collect_in_background`) you can call from the Tower | **ADOPT** (embed) |
| 2 | [Syllo/nvtop](https://github.com/Syllo/nvtop) | 11,106 | — | 2026-10-04 | Multi-vendor (NVIDIA/AMD/Intel) TUI monitor | **ADOPT** (TUI reference) |
| 3 | [utkuozdemir/nvidia_gpu_exporter](https://github.com/utkuozdemir/nvidia_gpu_exporter) | 1,573 | MIT | 2026-10-26 | Prometheus exporter via `nvidia-smi` | **WIRE** (if you want Prometheus) |
| 4 | [NVIDIA/dcgm-exporter](https://github.com/NVIDIA/dcgm-exporter) | 1,915 | Apache-2.0 | 2026-09-18 | Official NVIDIA DCGM Prometheus exporter | **SKIP** (overkill for a laptop) |
| 5 | [netdata/netdata](https://github.com/netdata/netdata) | 81,134 | GPL-3.0 | 2026-10-26 | Full-stack observability, GPU plugins, auto-dashboards | **SKIP** (heavy; nvitop is enough) |
| 6 | **pynvml** / **nvidia-ml-py** | — | — | current | Direct NVML Python bindings — what nvitop wraps | **WIRE** (if you want zero-dep) |

**Wiring note:** `nvitop` is the pick — it's pure Python, Apache-2.0, and exposes:
```python
from nvitop import api
api.gpuinfo()          # per-GPU: name, total_memory, used_memory, utilization, temperature
api.collect_in_background(...)  # non-blocking sampler
```
Drop a `/api/gpu` route in the Tower that returns NVML + Ollama's `/api/ps` merged →
true "what's using my VRAM right now" per model and per process.

---

## Track 8 — Local Media-Gen Servers (OpenAI-compatible endpoints)

| # | Repo | ★ | License | Last push | What it does | Port / API | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | [remsky/Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI) | 5,593 | Apache-2.0 | 2026-10-23 | Dockerized OpenAI-compat TTS (Kokoro-82M), streaming | `:8880/v1/audio/speech` | **ADOPT** |
| 2 | [speaches-ai/speaches](https://github.com/speaches-ai/speaches) | 3,736 | MIT | 2026-10-22 | "Ollama for TTS/STT" — faster-whisper + Piper/Kokoro, OpenAI-compat | `/v1/audio/transcriptions`, `/v1/audio/speech` | **ADOPT** |
| 3 | [Comfy-Org/ComfyUI](https://github.com/Comfy-Org/ComfyUI) | 143,097 | GPL-3.0 | 2026-10-26 | Node-based diffusion GUI + **native API mode** (`/prompt`); runs Flux, SD, video models | `:8188` | **ADOPT** |
| 4 | [pnyxai/comfyui-openai-api](https://github.com/pnyxai/comfyui-openai-api) | 18 | — | 2025-11 | Rust reverse-proxy: `/v1/images/generations` → ComfyUI | — | **SKIP** (stale) |
| 5 | [matatonic/openedai-images-flux](https://github.com/matatonic/openedai-images-flux) | — | — | **ARCHIVED 2026-01-30** | Was the Flux→OpenAI shim | — | **SKIP** (archived) |
| 6 | [fishaudio/fish-speech](https://github.com/fishaudio/fish-speech) | 33,406 | — | 2026-10-14 | SOTA TTS w/ API server | — | **ADOPT** (alt to Kokoro) |
| 7 | **Chatterbox** (resemble-ai) | ~10k *(via web)* | MIT | 2026 | High-quality TTS with emotion control | — | **ADOPT** (alt) |
| 8 | **Qwen3-TTS** / **CosyVoice2** | — | — | 2026 | Alibaba TTS, good multilingual | — | **ADOPT** (alt) |
| 9 | **XTTS-v2** (Coqui) | 46.1k *(via web)* | **non-commercial** | 2024 | Voice-cloning TTS | — | **SKIP** (license) |
| 10 | [ggml-org/whisper.cpp](https://github.com/ggml-org/whisper.cpp) | ~54.7k *(via web)* | MIT | 2026 | Local STT, C/C++, fast on CPU | — | **ADOPT** (STT side) |
| 11 | [Wan2.1](https://github.com/Wan-Video/Wan2.1) | ~15k *(via web)* | Apache-2.0 | 2026 | Local video gen (Alibaba), runs via ComfyUI | — | **ADOPT** (via Comfy) |
| 12 | [Rudrabha/Wav2Lip](https://github.com/Rudrabha/Wav2Lip) | 13,258 | — | 2025-06-22 | Lip-sync talking-head from audio+video | — | **SKIP** (stale-ish) |
| 13 | [m-bain/whisperX](https://github.com/m-bain/whisperX) | 24,855 | BSD-2 | 2026-10-22 | Whisper + word-level timestamps + diarization | — | **ADOPT** (caption side) |

**Wiring notes:**
- **TTS:** Kokoro-FastAPI on `:8880` — one `docker run`, OpenAI `/v1/audio/speech` works
  out of the box. Wire as an app in `apps.json`.
- **STT:** speaches (MIT, `:8000` or similar) gives OpenAI `/v1/audio/transcriptions`.
  Or whisper.cpp for pure-CPU.
- **Image:** ComfyUI has a native API (`POST /prompt`) but **not** OpenAI-compat. Either
  write a ~50-line FastAPI shim in the Tower, or use a maintained proxy (the two open
  ones found are both stale — this is a gap worth filling yourself).
- **Video:** Wan2.1 / LTX-Video run through ComfyUI's API — same shim applies.

---

## Top 8 Highest-Leverage Picks

Ranked by (impact on the Tower) × (effort to wire).

1. **LangGraph `interrupt()` / durable-approval pattern** — *STEAL*.
   The Tower's approval gate already works; this upgrades it to survive restarts,
   adds risk-tiering, and gives an audit trail. ~200 lines.
2. **nvitop Python API** — *ADOPT*.
   `pip install nvitop` + merge with Ollama's `/api/ps` → a real `/api/gpu` route showing
   per-model VRAM. Apache-2.0, actively pushed today.
3. **Kokoro-FastAPI + speaches** — *ADOPT*.
   Two `docker run`s give the Tower OpenAI-compat TTS (`:8880`) and STT. Instantly makes
   the Operator voice-capable. MIT/Apache.
4. **ComfyUI + a thin OpenAI-image shim** — *ADOPT/WRITE*.
   143k★, GPL, native API. The missing piece is a ~50-line `/v1/images/generations`
   → Comfy `/prompt` proxy in the Tower itself (both existing proxies are stale).
5. **mnfst/awesome-free-llm-apis + 4 new providers** — *WIRE*.
   Add Cerebras, Cloudflare Workers AI, HuggingFace Inference Providers, Scaleway to
   `tower/providers.py`. Keep the list on a weekly cron — GitHub Models and SambaNova
   both died this year without notice.
6. **Qwen3.5-4B** — *ADOPT* as the "deep" tier next to Needle 3.
   TAU2 79.9 in a 4B dense that fits 8GB. Keep Needle 3 as the fast router; promote to
   Qwen3.5-4B when multi-step reasoning is needed.
7. **Google official MCP servers (`google/mcp`) + `gws` CLI** — *ADOPT*.
   The live Gmail/Drive/Calendar path (GongRzhe's Gmail-MCP is archived). OAuth 2.0,
   official, Apache-2.0. Pairs with ZubeidHendricks' YouTube MCP server.
8. **LiteLLM / Portkey fallback + cooldown logic** — *STEAL*.
   The Tower's `router.py` already walks a chain. Steal the circuit-breaker +
   jittered-backoff + per-key-spend model from these two (both MIT, both pushed this
   week).

---

## Traps to avoid (verified 2026-10-26)

- **GitHub Models** — retired 2026-07-30. Do not add.
- **SambaNova free tier** — discontinued; now a paid "Developer Tier" with earn-credits.
- **RouteLLM** (lm-sys) — 5,636★ but **last push 2024-08**. Stale; use LiteLLM instead.
- **n8n** — fair-code (Sustainable Use), **not MIT**. Fine for self-host, not for
  redistribution.
- **Open WebUI** — frontend BSD-3, but the backend is a **custom license**. Read before
  embedding.
- **instagrapi** — Instagram Private API. Real account-ban risk. Publish via the official
  Graph API; use instagrapi only for reads/DMs you can afford to lose.
- **matatonic/openedai-images-flux** — archived 2026-01-30. Skip.
- **pnyxai/comfyui-openai-api** — 18★, last push 2025-11. Stale.
- **Cerebras free-tier numbers conflict** across sources (card vs no-card, 1M vs 5 RPM).
  Test empirically before relying on it.

**2026-10-26 correction (ZCode):** Kokoro-FastAPI's images are GONE from both
ghcr.io and docker hub (unauthorized on every tag, checked live) — the #1
ADOPT pick can't be pulled. The pivot actually shipped: speaches (#2) serves
**both** sides — Kokoro TTS (`/v1/audio/speech`,
`speaches-ai/Kokoro-82M-v1.0-ONNX-fp16`) and faster-whisper STT — in one
rootless podman CPU container on `:8000`, registered as a tower app, wired
into `/api/studio/tts` + the new `/api/studio/stt`. GPU untouched (bonsai's).
