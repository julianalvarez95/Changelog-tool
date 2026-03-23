"""
Loads and validates config.yaml + .env variables.
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent


def load_config(config_path: str = None) -> dict:
    """Load and validate config.yaml. Returns merged config dict."""
    load_dotenv(BASE_DIR / ".env")

    config_file = Path(config_path) if config_path else BASE_DIR / "config.yaml"
    if not config_file.exists():
        print(f"[ERROR] config.yaml not found at {config_file}", file=sys.stderr)
        sys.exit(1)

    with open(config_file) as f:
        config = yaml.safe_load(f)

    _inject_env_secrets(config)
    _validate(config)
    return config


def _inject_env_secrets(config: dict) -> None:
    """Inject environment variables into config for convenience."""
    config["_env"] = {
        "github_token": os.getenv("GITHUB_TOKEN"),
        "bitbucket_api_token": os.getenv("BITBUCKET_API_TOKEN"),
        "slack_bot_token": os.getenv("SLACK_BOT_TOKEN"),
        "gmail_address": os.getenv("GMAIL_ADDRESS"),
        "gmail_app_password": os.getenv("GMAIL_APP_PASSWORD"),
        "openai_api_key": os.getenv("OPENAI_API_KEY"),
    }


def _validate(config: dict) -> None:
    """Warn about missing credentials for configured integrations."""
    env = config.get("_env", {})
    dist = config.get("distribution", {})
    repos = config.get("repositories", [])

    has_github = any(r.get("provider") == "github" for r in repos)
    has_bitbucket = any(r.get("provider") == "bitbucket" for r in repos)

    if has_github and not env.get("github_token"):
        print("[WARN] GITHUB_TOKEN not set but GitHub repos are configured.", file=sys.stderr)
    if has_bitbucket and not env.get("bitbucket_api_token"):
        print("[WARN] BITBUCKET_API_TOKEN not set but Bitbucket repos are configured.", file=sys.stderr)
    if dist.get("slack") and not env.get("slack_bot_token"):
        print("[WARN] SLACK_BOT_TOKEN not set but Slack distribution is configured.", file=sys.stderr)
    if dist.get("email") and (not env.get("gmail_address") or not env.get("gmail_app_password")):
        print("[WARN] GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set but email distribution is configured.", file=sys.stderr)
