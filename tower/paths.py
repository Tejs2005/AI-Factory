"""Fixed filesystem locations for the AI Tower."""
from pathlib import Path

TOWER_ROOT = Path(__file__).resolve().parent.parent          # .../assets/ai-tower
CONFIG_DIR = TOWER_ROOT / "config"
LOGS_DIR = TOWER_ROOT / "logs"
STATIC_DIR = TOWER_ROOT / "static"
DOCS_DIR = TOWER_ROOT / "docs"

APPS_FILE = CONFIG_DIR / "apps.json"                          # app registry (editable)
STATE_FILE = CONFIG_DIR / "tower.json"                        # user state (selected models etc.)

BRAIN = Path.home() / ".ai-factory"                    # optional brain library (skills + rules)
SECRETS_DIR = Path.home() / ".factory-secrets"          # keys live here, never copied out
DEAD_KEYS_DOC = SECRETS_DIR / "DEAD-KEYS-2026-10-25.md"

LOCALAI_DIR = Path.home() / "localai"     # EDIT ME: wherever your LocalAI lives
LOCALAI_BIN = LOCALAI_DIR / "local-ai"

OLLAMA_BASE = "http://127.0.0.1:11434/v1"
OLLAMA_URL = "http://127.0.0.1:11434"                            # native API (/api/*)
LOCALAI_BASE = "http://127.0.0.1:8080/v1"
BRAIN_CONSOLE = "http://127.0.0.1:8420"

TOWER_HOST = "127.0.0.1"
TOWER_PORT = 7425


def ensure_dirs() -> None:
    for d in (CONFIG_DIR, LOGS_DIR, STATIC_DIR, DOCS_DIR):
        d.mkdir(parents=True, exist_ok=True)
