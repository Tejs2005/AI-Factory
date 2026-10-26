# Awesome Repos for the AI Tower

Curated catalog for Tejas's local AI control tower (Linux laptop).
Every repo below was verified live against the GitHub API on **2026-10-26** (star counts, license, archived status, last-push date). All are non-archived and receiving pushes in 2025–2026 unless explicitly flagged as *stale*.

---

## Top 10 picks overall

1. **[n8n-io/n8n](https://github.com/n8n-io/n8n)** (208k ★) — The control-tower backbone: visual AI workflows + 400+ integrations, self-hosted via Docker.
2. **[open-webui/open-webui](https://github.com/open-webui/open-webui)** (157k ★) — Local chat UI for Ollama/OpenAI-compatible models; the front door of the tower.
3. **[ollama/ollama](https://github.com/ollama/ollama)** (185k ★) — One-line local model runtime; everything else plugs into it.
4. **[gitroomhq/postiz-app](https://github.com/gitroomhq/postiz-app)** (38k ★) — Self-hosted Buffer/Later replacement (10+ platforms, agent-friendly API).
5. **[browser-use/browser-use](https://github.com/browser-use/browser-use)** (119k ★) — Python library that lets LLMs drive a real browser.
6. **[trycua/cua](https://github.com/trycua/cua)** (31k ★) — Open computer-use drivers + Linux/macOS/Windows sandboxes for AI desktop control.
7. **[knadh/listmonk](https://github.com/knadh/listmonk)** (24k ★) — Single-binary self-hosted newsletter/email engine (Mailchimp alternative).
8. **[subzeroid/instagrapi](https://github.com/subzeroid/instagrapi)** (7k ★) — The only real Instagram Private API library (post, DM, story automation).
9. **[upscayl/upscayl](https://github.com/upscayl/upscayl)** (51k ★) — Local AI image upscaler with a desktop GUI (Photoshop-adjacent workhorse).
10. **[All-Hands-AI/OpenHands](https://github.com/OpenHands/OpenHands)** (92k ★) — Autonomous AI dev agent that can run a shell, edit files and browse, fully self-hostable.

---

## 1. Social / media automation

| Repo | Stars | What it replaces / does | Install | License |
|---|---|---|---|---|
| [gitroomhq/postiz-app](https://github.com/gitroomhq/postiz-app) | ~37.9k | Self-hosted Buffer/Later: schedule & publish to X, LinkedIn, Instagram, TikTok, YouTube, Facebook via one calendar; API + agent CLI ([gitroomhq/postiz-agent](https://github.com/gitroomhq/postiz-agent), 550★) | `docker compose up -d` (ghcr.io/postiz) | AGPL-3.0 |
| [brightbeanxyz/brightbean-studio](https://github.com/brightbeanxyz/brightbean-studio) | ~2.6k | Newer self-hosted social media management studio — schedule/publish across 10+ platforms, active 2026 | `docker compose up -d` | AGPL-3.0 |
| [subzeroid/instagrapi](https://github.com/subzeroid/instagrapi) | ~7.0k | Instagram Private API in Python: post photos/reels, DMs, stories, hashtag/user scraping (original `adw0rd/instagrapi` now redirects here) | `pipx install instagrapi` | custom (free lib + HikerAPI SaaS) |
| [davidteather/TikTok-Api](https://github.com/davidteather/TikTok-Api) | ~6.7k | Unofficial TikTok API: read trending, user data, post metadata (upload still via Postiz/official API) | `pipx install TikTokApi` | MIT |
| [rushindrasinha/youtube-shorts-pipeline](https://github.com/rushindrasinha/youtube-shorts-pipeline) | ~2.3k | End-to-end Shorts factory: news → script → AI visuals → voiceover → captions → **YouTube upload** | `git clone` + Python deps (`pip install -r requirements.txt`) | MIT |
| [tokland/youtube-upload](https://github.com/tokland/youtube-upload) | ~2.2k | Classic CLI: upload videos to YouTube from the terminal via YouTube Data API. ⚠️ stale (last push 2024-04) but still the most-starred pure uploader | `pipx install youtube-upload` (or clone) | Unlicense-ish (no LICENSE file) |

*Also verified:* [fawazahmed0/youtube-uploader](https://github.com/fawazahmed0/youtube-uploader) (458★, MIT, no-quota-limit uploader, pushed 2026-01) · [streamlink/streamlink](https://github.com/streamlink/streamlink) (11.9k★, BSD-2, livestream piping) · [getopenpost/openpost](https://github.com/getopenpost/openpost) (772★, AGPL, Postiz alternative).

## 2. Email automation

| Repo | Stars | What it replaces / does | Install | License |
|---|---|---|---|---|
| [knadh/listmonk](https://github.com/knadh/listmonk) | ~24.0k | Self-hosted Mailchimp: newsletters, campaigns, drip sequences, subscriber segmentation, transactional API. Single Go binary + Postgres | `docker compose up -d` or single binary | AGPL-3.0 |
| [mautic/mautic](https://github.com/mautic/mautic) | ~10.9k | Self-hosted marketing automation (ActiveCampaign/HubSpot-lite): lead scoring, drip campaigns, landing pages, CRM | `composer create-project mautic/mautic` or Docker | GPL-3.0 (with exceptions) |
| [Mailtrain-org/mailtrain](https://github.com/Mailtrain-org/mailtrain) | ~5.8k | Self-hosted newsletter app with list management & campaign editor | `docker compose up -d` | GPL-3.0 |
| [googleworkspace/cli](https://github.com/googleworkspace/cli) | ~31.9k | Official Google Workspace CLI — one tool for Gmail, Drive, Calendar, Sheets, Chat, Admin; ideal scripting target for the tower | `brew install gws` / download binary | Apache-2.0 |
| [googleapis/google-api-python-client](https://github.com/googleapis/google-api-python-client) | ~9.0k | The official Python client — the standard way to script Gmail (send, label, thread, attachments) | `pipx install google-api-python-client` | Apache-2.0 |
| [huginn/huginn](https://github.com/huginn/huginn) | ~50.1k | "Agents that monitor and act for you" — IFTTT/Zapier email agents: watch inboxes/feeds, transform, send mail, webhooks | `docker compose up -d` | MIT |

## 3. Workflow automation / self-hosted Zapier alternatives

| Repo | Stars | What it replaces / does | Install | License |
|---|---|---|---|---|
| [n8n-io/n8n](https://github.com/n8n-io/n8n) | ~208.6k | Fair-code Zapier/Make with native AI agents + MCP; 400+ integrations, self-host | `docker run -d -p 5678:5678 -v n8n_data:/home/node/.n8n ghcr.io/n8nio/n8n` | Sustainable Use (fair-code) |
| [kestra-io/kestra](https://github.com/kestra-io/kestra) | ~30.0k | Declarative orchestrator for workflows across data, infra & business processes (Airflow/Temporal-class, but with a nice UI) | `docker run --pull=always -p 8080:8080 ghcr.io/kestra-io/kestra:latest` | Apache-2.0 |
| [activepieces/activepieces](https://github.com/activepieces/activepieces) | ~25.2k | MIT n8n alternative with ~400 MCP servers for AI agents; Zapier-style piece ecosystem | `docker compose up -d` | MIT (pieces) / EE bits |
| [node-red/node-red](https://github.com/node-red/node-red) | ~23.8k | Low-code event-flow programming (the classic for IoT + quick automations), browser-based editor | `npm install -g --unsafe-perm node-red` or Docker | Apache-2.0 |
| [windmill-labs/windmill](https://github.com/windmill-labs/windmill) | ~18.3k | Code-first workflows + internal apps in Python/TS/Go on a Rust orchestrator; Retool + n8n in one | `docker compose up -d` or `curl -fsSL https://app.windmill.dev/install.sh \| sh` | AGPL-3.0 / EE |
| [automatisch/automatisch](https://github.com/automatisch/automatisch) | ~14.0k | Straightforward open-source Zapier: queue-based, minimal, self-host, no per-task pricing | `docker compose up -d` | Sustainable Use (fair-code) |

## 4. Media creation — free alternatives to paid apps

| Repo | Stars | What it replaces / does | Install | License |
|---|---|---|---|---|
| [obsproject/obs-studio](https://github.com/obsproject/obs-studio) | ~78.2k | Screen recording + live streaming (the Camtasia/XSplit/Zoom-record default) | `sudo apt install obs-studio` or `flatpak install com.obsproject.Studio` | GPL-2.0 |
| [upscayl/upscayl](https://github.com/upscayl/upscayl) | ~51.1k | Local AI image upscaler GUI (Real-ESRGAN class models, batch, 100% offline) | AppImage from releases / `flatpak install io.github.upscayl.upscayl` | AGPL-3.0 |
| [ggerganov/whisper.cpp](https://github.com/ggml-org/whisper.cpp) | ~54.7k | Offline speech-to-text (captions, transcripts) in pure C/C++, runs fast on CPU | `sudo apt install whisper-cpp` / build from source / `pipx` bindings | MIT |
| [KDE/kdenlive](https://github.com/KDE/kdenlive) | ~5.9k | Full non-linear video editor — the CapCut/Premiere alternative on Linux | `sudo apt install kdenlive` or `flatpak install org.kde.kdenlive` | GPL-3.0 |
| [mltframework/shotcut](https://github.com/mltframework/shotcut) | ~15.5k | Simpler cross-platform video editor, wide format support, great for quick cuts | `sudo apt install shotcut` / AppImage / Flatpak | GPL-3.0 |
| [GNOME/gimp](https://github.com/GNOME/gimp) | ~6.5k | GIMP 3 — the Photoshop alternative (read-only mirror of gitlab.gnome.org) | `sudo apt install gimp` | GPL-3.0 |

*Also verified (shortlisted, not counted):* [k2-fsa/sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) (15.5k★, Apache-2.0, active — **TTS + STT + diarization**, best pick for local voice) · [darktable-org/darktable](https://github.com/darktable-org/darktable) (13.3k★, GPL-3.0, Lightroom alternative) · [jliljebl/flowblade](https://github.com/jliljebl/flowblade) (3.1k★, Linux-native editor) · [Comfy-Org/ComfyUI](https://github.com/Comfy-Org/ComfyUI) (143k★, local diffusion image/video generation) · [dromara/yft-design](https://github.com/dromara/yft-design) (1.7k★, MIT, self-hosted Canva-style design tool) · [xinntao/Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) (37.2k★, ⚠️ research code, last push 2024-08 — superseded by Upscayl for daily use) · [coqui-ai/TTS](https://github.com/coqui-ai/TTS) (46.1k★, ⚠️ effectively unmaintained, last push 2024-08 — use sherpa-onnx instead).

## 5. Self-hosted AI app catalog

| Repo | Stars | What it replaces / does | Install | License |
|---|---|---|---|---|
| [ollama/ollama](https://github.com/ollama/ollama) | ~184.8k | Local LLM runtime (Qwen, Llama, Gemma, gpt-oss…) with an HTTP API everything else connects to | `curl -fsSL https://ollama.com/install.sh \| sh` | MIT |
| [open-webui/open-webui](https://github.com/open-webui/open-webui) | ~156.8k | Self-hosted ChatGPT-style UI for Ollama + any OpenAI-compatible API; RAG, tools, multi-user | `docker run -d -p 3000:8080 -v open-webui:/app/backend/data ghcr.io/open-webui/open-webui:main` or `pipx install open-webui` | BSD-3-Clause (frontend) |
| [browser-use/browser-use](https://github.com/browser-use/browser-use) | ~119.2k | Python library making LLMs browse like a human (Playwright-backed); the automation glue for the tower | `pipx install browser-use` | MIT |
| [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) | ~91.9k | (formerly All-Hands-AI) Autonomous dev agent — shell, editor, browser in a sandbox; self-host with Docker | `docker run -it --rm --name openhands -p 3000:3000 -e SANDBOX_MOUNT_PATH=$PWD ghcr.io/all-hands-ai/openhands:latest` | MIT |
| [trycua/cua](https://github.com/trycua/cua) | ~31.0k | Computer-use 2.0: open drivers to control macOS/Linux/Windows desktops + cross-OS sandboxes for AI agents | `pipx install cua-agent` / see repo for sandbox images | MIT |
| [Skyvern-AI/skyvern](https://github.com/Skyvern-AI/skyvern) | ~23.3k | AI browser automation that works on screenshots + LLM reasoning (no brittle selectors); self-hosted Zapier-for-webforms | `docker compose up -d` | AGPL-3.0 |

## 6. Productivity free-alternative gems (top 5)

| Repo | Stars | What it replaces / does | Install | License |
|---|---|---|---|---|
| [syncthing/syncthing](https://github.com/syncthing/syncthing) | ~89.8k | Continuous P2P file sync — the Dropbox/iCloud replacement, no cloud account | `sudo apt install syncthing` + `systemctl enable --now syncthing@default` | MPL-2.0 |
| [AppFlowy-IO/AppFlowy](https://github.com/AppFlowy-IO/AppFlowy) | ~77.8k | Notion/OneNote alternative: offline-first notes, wikis, kanban with local AI | Desktop AppImage / Flatpak from releases | AGPL-3.0 |
| [dani-garcia/vaultwarden](https://github.com/dani-garcia/vaultwarden) | ~69.7k | Bitwarden-compatible password manager server in Rust — runs in ~30MB RAM | `docker compose up -d` | AGPL-3.0 |
| [laurent22/joplin](https://github.com/laurent22/joplin) | ~56.9k | Markdown notes with end-to-end encryption and sync — the Evernote replacement | AppImage / `sudo apt install joplin` (via Joplin Desktop) | AGPL-3.0 (app) |
| [calcom/cal.com](https://github.com/calcom/cal.com) | ~49.4k | Calendly/Cal.com scheduling infrastructure — self-hosted booking links & workflows | `git clone` + `pnpm i && pnpm build` or Docker | MIT |

*Runner-up verified:* [nextcloud/server](https://github.com/nextcloud/server) (37.3k★, AGPL-3.0) — full file-sync/calendar/contacts suite if Syncthing feels too minimal; [immich-app/immich](https://github.com/immich-app/immich) (117k★, AGPL-3.0) for the Google Photos side of the tower.

---

## Connectors

How to actually wire the tower into each platform (all verified to exist):

### YouTube
- **[googleapis/google-api-python-client](https://github.com/googleapis/google-api-python-client)** (~9.0k★, Apache-2.0) — official YouTube Data API v3 client (upload `videos.insert`, analytics, captions). `pipx install google-api-python-client` + OAuth2 client secret.
- **[googleworkspace/cli](https://github.com/googleworkspace/cli)** (~31.9k★, Apache-2.0) — scriptable one-liners for Workspace APIs without writing code.
- **[tokland/youtube-upload](https://github.com/tokland/youtube-upload)** (~2.2k★) — the classic "ytpost-style" CLI uploader (`youtube-upload --title=... file.mp4`). Stale but functional.
- **[fawazahmed0/youtube-uploader](https://github.com/fawazahmed0/youtube-uploader)** (~458★, MIT) — quota-friendly JS uploader, pushed 2026-01.
- **[rushindrasinha/youtube-shorts-pipeline](https://github.com/rushindrasinha/youtube-shorts-pipeline)** (~2.3k★, MIT) — full Shorts creation→upload pipeline to crib code from.
- Download/analysis side: **[yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp)** (~202k★, Unlicense) — grab captions/metadata of any channel for competitive research.

### Instagram
- **[subzeroid/instagrapi](https://github.com/subzeroid/instagrapi)** (~7.0k★) — the de-facto standard Instagram Private API for Python: login, upload photos/reels, DM automation, stories, hashtag feeds. (Note: `adw0rd/instagrapi` redirects here; the paid HikerAPI SaaS is bundled marketing — the library itself is free to use.)
- **[gitroomhq/postiz-app](https://github.com/gitroomhq/postiz-app)** (~37.9k★) — for *posting/scheduling* via the official **Meta Graph API** (`instagram_content_publish`), which is the ToS-safe route; use instagrapi for DM/engagement work.
- **[davidteather/TikTok-Api](https://github.com/davidteather/TikTok-Api)** (~6.7k★, MIT) — the TikTok side (unofficial; pair with Postiz's official TikTok connector for publishing).

### Gmail / email
- **[googleapis/google-api-python-client](https://github.com/googleapis/google-api-python-client)** — Gmail API (`gmail.users.messages.send`, labels, threads, attachments). Needs OAuth2 scope `https://www.googleapis.com/auth/gmail.modify`.
- **[googleapis/google-api-nodejs-client](https://github.com/googleapis/google-api-nodejs-client)** (~12.3k★, Apache-2.0) — same for Node/TS stacks.
- **[googleworkspace/cli](https://github.com/googleworkspace/cli)** — fastest way to test Gmail + Calendar + Sheets automation from a shell script.
- **[ahochsteger/gmail-processor](https://github.com/ahochsteger/gmail-processor)** (~585★, Apache-2.0, pushed 2026-10) — Apps Script library that turns Gmail rules (labels, attachments, regex) into automated actions — "Zapier for Gmail" without leaving Google's infra.
- **Sending newsletters/campaigns:** **[knadh/listmonk](https://github.com/knadh/listmonk)** — bring your own SMTP (e.g. Gmail SMTP, SES, or a local MTA); it exposes a full REST API so n8n/agent code can trigger campaigns programmatically.

### Glue note
n8n ships native nodes for YouTube/Google, Gmail and HTTP calls for Meta Graph API; Postiz ships an official REST API plus an agent CLI (`gitroomhq/postiz-agent`), and there are community bridges (`gitroomhq/postiz-n8n`, `LucasSovre/listmonk-n8n`, `rhnvrm/listmonk-mcp` — MCP server so Claude/OpenCode agents can drive listmonk directly).
