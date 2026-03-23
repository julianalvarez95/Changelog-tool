#!/usr/bin/env python3
"""
Changelog Generator — Entry point.

Usage:
    python changelog.py                          # run desde last_run hasta hoy
    python changelog.py --dry-run                # genera sin enviar
    python changelog.py --since 2025-03-10       # desde fecha específica
    python changelog.py --since 2025-03-10 --until 2025-03-17
    python changelog.py --only slack
    python changelog.py --only email
    python changelog.py --dry-run --save-markdown
"""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from src.config import load_config
from src.parser import categorize_commits
from src.generator import render
from src import fetchers  # noqa — ensure package is importable

BASE_DIR = Path(__file__).parent
LAST_RUN_FILE = BASE_DIR / "last_run.json"


# ── CLI ──────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate and distribute business-friendly changelogs."
    )
    parser.add_argument(
        "--config", default=None, help="Path to config.yaml (default: ./config.yaml)"
    )
    parser.add_argument(
        "--since",
        default=None,
        metavar="YYYY-MM-DD",
        help="Start date for commit range (overrides since_last_run)",
    )
    parser.add_argument(
        "--until",
        default=None,
        metavar="YYYY-MM-DD",
        help="End date for commit range (default: now)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate changelog but do not send it",
    )
    parser.add_argument(
        "--only",
        choices=["slack", "email"],
        default=None,
        help="Send only to this channel (default: both)",
    )
    parser.add_argument(
        "--save-markdown",
        action="store_true",
        help="Force saving markdown output (overrides config)",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM description enrichment",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Force LLM call even if cache exists for this period",
    )
    return parser.parse_args()


# ── Last-run persistence ─────────────────────────────────────────────────────

def load_last_run() -> dict:
    if LAST_RUN_FILE.exists():
        with open(LAST_RUN_FILE) as f:
            return json.load(f)
    return {"last_run": None, "changelogs_generated": 0}


def save_last_run(state: dict) -> None:
    with open(LAST_RUN_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── Date helpers ─────────────────────────────────────────────────────────────

def parse_date(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def resolve_dates(args, config: dict, last_run: dict):
    changelog_cfg = config.get("changelog", {})

    if args.until:
        until = parse_date(args.until)
    else:
        until = datetime.now(timezone.utc)

    if args.since:
        since = parse_date(args.since)
    elif changelog_cfg.get("since"):
        since = parse_date(changelog_cfg["since"])
    elif changelog_cfg.get("since_last_run") and last_run.get("last_run"):
        since = datetime.fromisoformat(last_run["last_run"]).replace(tzinfo=timezone.utc)
    else:
        # Default: last 7 days
        from datetime import timedelta
        since = until - timedelta(days=7)

    return since, until


# ── Cache helpers ────────────────────────────────────────────────────────────

def _get_cache_path(config: dict, since, until) -> Path | None:
    if not since or not until:
        return None
    output_dir = config.get("output", {}).get("output_dir", "./changelogs")
    key = f"{since.strftime('%Y-%m-%d')}_{until.strftime('%Y-%m-%d')}"
    return Path(output_dir) / ".intel_cache" / f"{key}.json"


# ── Fetching ─────────────────────────────────────────────────────────────────

def fetch_repo_commits(repo_cfg: dict, config: dict, since: datetime, until: datetime) -> list[dict]:
    env = config["_env"]
    provider = repo_cfg.get("provider", "").lower()

    if provider == "github":
        from src.fetchers.github import fetch_commits
        return fetch_commits(
            token=env["github_token"],
            owner=repo_cfg["owner"],
            repo=repo_cfg["repo"],
            branch=repo_cfg.get("branch", "main"),
            since=since,
            until=until,
        )
    elif provider == "bitbucket":
        from src.fetchers.bitbucket import fetch_commits
        return fetch_commits(
            api_token=env["bitbucket_api_token"],
            workspace=repo_cfg["workspace"],
            repo=repo_cfg["repo"],
            branch=repo_cfg.get("branch", "main"),
            since=since,
            until=until,
        )
    else:
        print(f"[WARN] Unknown provider '{provider}' for repo {repo_cfg.get('name')}. Skipping.", file=sys.stderr)
        return []


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    config = load_config(args.config)
    last_run = load_last_run()

    since, until = resolve_dates(args, config, last_run)

    print(f"\n[changelog] Generating changelog for period: {since.date()} → {until.date()}")
    print(f"[changelog] Repos: {len(config.get('repositories', []))}")

    # Fetch & categorize commits per repo (parallel)
    categorized: dict[str, dict] = {}
    repos = config.get("repositories", [])
    with ThreadPoolExecutor(max_workers=max(1, len(repos))) as executor:
        futures = {
            executor.submit(fetch_repo_commits, repo_cfg, config, since, until): repo_cfg
            for repo_cfg in repos
        }
        for future in as_completed(futures):
            repo_cfg = futures[future]
            name = repo_cfg.get("name", repo_cfg.get("repo", "unknown"))
            raw_commits = future.result()
            categorized[name] = (
                categorize_commits(raw_commits, name, config.get("categories"))
                if raw_commits
                else {key: [] for key in config.get("categories", {})}
            )

    total = sum(
        len(commits)
        for repo_cats in categorized.values()
        for commits in repo_cats.values()
    )
    print(f"[changelog] Total commits to include: {total}")

    # Generate cross-repo intelligence (single LLM call, with cache)
    intelligence = None
    if not args.no_llm and config.get("llm", {}).get("enabled"):
        from src.llm import generate_intelligence
        from src.postprocessor import validate_and_clean

        cache_file = _get_cache_path(config, since, until)
        if not args.no_cache and cache_file and cache_file.exists():
            raw_intelligence = json.loads(cache_file.read_text())
            print("[changelog] Intelligence loaded from cache.")
        else:
            raw_intelligence = generate_intelligence(categorized, config, since, until)
            if raw_intelligence is not None and cache_file:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(json.dumps(raw_intelligence, ensure_ascii=False, indent=2))

        if raw_intelligence is not None:
            intelligence = validate_and_clean(raw_intelligence, config)
            h = len(intelligence["highlights"])
            f = len(intelligence["fixes"])
            i = len(intelligence["improvements"])
            print(f"[changelog] Intelligence: {h} highlights, {f} fixes, {i} improvements")
        else:
            print("[changelog] Intelligence failed — using categorized fallback.", file=sys.stderr)

    # Render templates
    slack_text    = render(categorized, config, since, until, "slack.j2",       intelligence=intelligence)
    email_html    = render(categorized, config, since, until, "email.html.j2",  intelligence=intelligence)
    markdown_text = render(categorized, config, since, until, "markdown.md.j2", intelligence=intelligence)

    # Always print to console
    print("\n" + "─" * 60)
    print(slack_text)
    print("─" * 60 + "\n")

    # Save markdown
    output_cfg = config.get("output", {})
    should_save = args.save_markdown or output_cfg.get("save_markdown", False)
    if should_save:
        output_dir = Path(output_cfg.get("output_dir", "./changelogs"))
        output_dir.mkdir(parents=True, exist_ok=True)
        md_file = output_dir / f"changelog-{until.strftime('%Y-%m-%d')}.md"
        md_file.write_text(markdown_text, encoding="utf-8")
        print(f"[changelog] Markdown saved to {md_file}")

    if args.dry_run:
        print("[changelog] --dry-run: skipping distribution.")
        return

    dist_cfg = config.get("distribution", {})
    env = config["_env"]

    # Slack
    if args.only in (None, "slack") and dist_cfg.get("slack"):
        from src.distributors.slack import send as slack_send
        channel = dist_cfg["slack"].get("channel", "#general")
        slack_send(token=env["slack_bot_token"], channel=channel, text=slack_text)

    # Email
    if args.only in (None, "email") and dist_cfg.get("email"):
        from src.distributors.email import send as email_send
        email_cfg = dist_cfg["email"]
        changelog_cfg = config.get("changelog", {})
        period_label = f"{since.strftime('%-d %b')} — {until.strftime('%-d %b %Y')}"
        subject = email_cfg.get("subject", "Novedades {period}").format(
            title=changelog_cfg.get("title", "Changelog"),
            period=period_label,
        )
        email_send(
            gmail_address=env["gmail_address"],
            app_password=env["gmail_app_password"],
            recipients=email_cfg.get("recipients", []),
            subject=subject,
            html_body=email_html,
            from_name=email_cfg.get("from_name", "Changelog Bot"),
        )

    # Update last_run
    last_run["last_run"] = until.isoformat()
    last_run["changelogs_generated"] = last_run.get("changelogs_generated", 0) + 1
    save_last_run(last_run)
    print(f"[changelog] Done. last_run.json updated to {until.isoformat()}")


if __name__ == "__main__":
    main()
