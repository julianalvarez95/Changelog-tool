"""
Config API route: expose operator-facing configuration for the UI.

GET /config — returns available distribution targets, tones, and last_run date.
             Never exposes credentials (_env).
"""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from src.config import load_config

router = APIRouter(prefix="/config", tags=["config"])

BASE_DIR = Path(__file__).parent.parent.parent
LAST_RUN_FILE = BASE_DIR / "last_run.json"

AVAILABLE_TONES = ["business", "technical", "executive"]


@router.get("")
def get_config():
    """Return operator-facing config: distribution targets, available tones, last_run date.

    Used by the UI to populate form options on load.
    """
    try:
        config = load_config()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load config: {exc}")

    dist_cfg = config.get("distribution", {})
    changelog_cfg = config.get("changelog", {})

    # Distribution targets (metadata only — no credentials)
    slack_info = None
    slack_cfg = dist_cfg.get("slack", {})
    if slack_cfg and slack_cfg.get("channel"):
        slack_info = {"channel": slack_cfg["channel"]}

    email_info = None
    email_cfg = dist_cfg.get("email", {})
    if email_cfg and email_cfg.get("recipients"):
        email_info = {
            "recipients": email_cfg["recipients"],
            "subject_template": email_cfg.get("subject", "Changelog {title} - {period}"),
            "from_name": email_cfg.get("from_name", "Changelog Bot"),
        }

    # Last run date
    last_run: str | None = None
    if LAST_RUN_FILE.exists():
        try:
            data = json.loads(LAST_RUN_FILE.read_text())
            last_run = data.get("last_run")
        except Exception:
            pass

    return {
        "distribution": {
            "slack": slack_info,
            "email": email_info,
        },
        "tones": AVAILABLE_TONES,
        "current_tone": changelog_cfg.get("tone", "business"),
        "last_run": last_run,
        "title": changelog_cfg.get("title", "Changelog"),
    }
