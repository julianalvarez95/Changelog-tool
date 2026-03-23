"""
Background pipeline runner for web-triggered changelog jobs.

run_pipeline() is called by FastAPI BackgroundTasks and runs synchronously
in a thread. It replicates changelog.py's pipeline logic, writing stage
progress to SQLite as it proceeds.

Decisions from 01-CONTEXT.md:
- D-01: Continue on partial repo fetch failure
- D-02: Final status = "partial" if any repo failed, "done" if all succeeded
- D-03: LLM failure -> status = "failed" (no fallback)
"""
import json
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from src.config import load_config
from src.parser import categorize_commits
from src.generator import render
from web.db import update_job_status, update_job_result

BASE_DIR = Path(__file__).parent.parent
LAST_RUN_FILE = BASE_DIR / "last_run.json"


def _fetch_repo(repo_cfg: dict, config: dict, since: datetime, until: datetime) -> tuple[str, list[dict]]:
    """Fetch commits for a single repo. Returns (repo_name, commits_list).
    Raises on network/auth error — caller catches and records failure."""
    env = config["_env"]
    provider = repo_cfg.get("provider", "").lower()
    name = repo_cfg.get("name", repo_cfg.get("repo", "unknown"))

    if provider == "github":
        from src.fetchers.github import fetch_commits
        commits = fetch_commits(
            token=env["github_token"],
            owner=repo_cfg["owner"],
            repo=repo_cfg["repo"],
            branch=repo_cfg.get("branch", "main"),
            since=since,
            until=until,
        )
    elif provider == "bitbucket":
        from src.fetchers.bitbucket import fetch_commits
        commits = fetch_commits(
            username=env["bitbucket_username"],
            app_password=env["bitbucket_app_password"],
            workspace=repo_cfg["workspace"],
            repo=repo_cfg["repo"],
            branch=repo_cfg.get("branch", "main"),
            since=since,
            until=until,
        )
    else:
        return name, []
    return name, commits


def _update_last_run(until: datetime) -> None:
    """Update last_run.json atomically — same file used by CLI."""
    state = {"last_run": None, "changelogs_generated": 0}
    if LAST_RUN_FILE.exists():
        try:
            with open(LAST_RUN_FILE) as f:
                state = json.load(f)
        except Exception:
            pass
    state["last_run"] = until.isoformat()
    state["changelogs_generated"] = state.get("changelogs_generated", 0) + 1
    # Atomic write: write to temp then os.replace (POSIX atomic)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=BASE_DIR, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp_path, LAST_RUN_FILE)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def run_pipeline(job_id: str, since_str: str, until_str: str) -> None:
    """
    Run the full changelog pipeline for a job.
    Called synchronously by FastAPI BackgroundTasks in a thread.

    Args:
        job_id: UUID string from db.create_job()
        since_str: ISO date string "YYYY-MM-DD"
        until_str: ISO date string "YYYY-MM-DD"
    """
    try:
        since = datetime.strptime(since_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        until = datetime.strptime(until_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)

        # Load config once — never reload mid-pipeline (Pitfall 4)
        config = load_config()

        # Stage 1: Fetching
        update_job_status(job_id, "fetching", "Fetching commits from repositories...")

        repos = config.get("repositories", [])
        categorized: dict[str, dict] = {}
        failed_repos: list[str] = []

        with ThreadPoolExecutor(max_workers=max(1, len(repos))) as executor:
            futures = {
                executor.submit(_fetch_repo, repo_cfg, config, since, until): repo_cfg
                for repo_cfg in repos
            }
            for future in as_completed(futures):
                repo_cfg = futures[future]
                name = repo_cfg.get("name", repo_cfg.get("repo", "unknown"))
                try:
                    repo_name, raw_commits = future.result()
                    categorized[repo_name] = (
                        categorize_commits(raw_commits, repo_name, config.get("categories"))
                        if raw_commits
                        else {key: [] for key in config.get("categories", {})}
                    )
                except Exception as exc:
                    # D-01: continue on partial fetch failure
                    failed_repos.append(name)
                    print(f"[tasks] Repo fetch failed for {name}: {exc}", file=sys.stderr)

        # If all repos failed, mark failed and stop
        if not categorized:
            update_job_result(
                job_id,
                status="failed",
                failed_repos=failed_repos,
            )
            return

        # Stage 2: Parsing (categorize_commits already called above inline with fetching)
        update_job_status(job_id, "parsing", "Parsing and categorizing commits...")

        # Stage 3: LLM intelligence (D-03: failure = job failed, no fallback)
        intelligence = None
        if config.get("llm", {}).get("enabled"):
            update_job_status(job_id, "generating", "Generating changelog with LLM...")
            from src.llm import generate_intelligence
            from src.postprocessor import validate_and_clean
            raw_intelligence = generate_intelligence(categorized, config, since, until)
            if raw_intelligence is None:
                # D-03: LLM failed — operator must retry
                update_job_result(
                    job_id,
                    status="failed",
                    failed_repos=failed_repos if failed_repos else None,
                )
                return
            intelligence = validate_and_clean(raw_intelligence, config)
        else:
            update_job_status(job_id, "generating", "Rendering changelog...")

        # Render all 3 templates
        slack_text = render(categorized, config, since, until, "slack.j2", intelligence=intelligence)
        email_html = render(categorized, config, since, until, "email.html.j2", intelligence=intelligence)
        markdown_text = render(categorized, config, since, until, "markdown.md.j2", intelligence=intelligence)

        # Determine final status: D-01/D-02
        final_status = "partial" if failed_repos else "done"

        update_job_result(
            job_id,
            status=final_status,
            slack_text=slack_text,
            email_html=email_html,
            markdown_text=markdown_text,
            intelligence_json=intelligence,
            failed_repos=failed_repos if failed_repos else None,
        )

        # Update last_run.json atomically (same file used by CLI)
        _update_last_run(until)

    except Exception as exc:
        # Top-level catch: any unexpected failure marks job as failed
        print(f"[tasks] Unexpected pipeline error for job {job_id}: {exc}", file=sys.stderr)
        try:
            update_job_result(job_id, status="failed")
        except Exception:
            pass
