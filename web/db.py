"""
SQLite CRUD layer for changelog job records.
Database file: ./changelogs/jobs.db (relative to project root)
"""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent  # project root
DB_PATH = BASE_DIR / "changelogs" / "jobs.db"

# Job status values (per 01-CONTEXT.md decisions):
# queued → fetching → parsing → generating → done | failed | partial
# "partial" means some repo fetches failed but job continued (D-01, D-02)
# "failed" means LLM call failed — operator must retry (D-03)

CREATE_JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'queued',
    progress_message TEXT,
    since TEXT NOT NULL,
    until TEXT NOT NULL,
    config_snapshot TEXT,
    slack_text TEXT,
    email_html TEXT,
    markdown_text TEXT,
    intelligence_json TEXT,
    failed_repos TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
)
"""


def init_db() -> None:
    """Create the database file and jobs table if they don't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute(CREATE_JOBS_TABLE)
        conn.commit()
    finally:
        conn.close()


def get_db():
    """FastAPI dependency: yields an open sqlite3 connection, closes after request."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def create_job(since_str: str, until_str: str, config_snapshot: dict | None = None) -> str:
    """Insert a new job row with status='queued'. Returns the job id (UUID)."""
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    snapshot_json = json.dumps(config_snapshot) if config_snapshot else None
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            """INSERT INTO jobs (id, status, progress_message, since, until, config_snapshot, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (job_id, "queued", "Job queued", since_str, until_str, snapshot_json, now),
        )
        conn.commit()
    finally:
        conn.close()
    return job_id


def get_job(job_id: str) -> dict | None:
    """Return job row as dict, or None if not found."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_job_status(job_id: str, status: str, progress_message: str) -> None:
    """Update job status and progress message (used during pipeline stages)."""
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute(
            "UPDATE jobs SET status = ?, progress_message = ? WHERE id = ?",
            (status, progress_message, job_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_job_result(
    job_id: str,
    status: str,          # "done" | "partial" | "failed"
    slack_text: str | None = None,
    email_html: str | None = None,
    markdown_text: str | None = None,
    intelligence_json: dict | None = None,
    failed_repos: list[str] | None = None,
) -> None:
    """Write rendered outputs and mark job complete/partial/failed."""
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute(
            """UPDATE jobs
               SET status = ?,
                   slack_text = ?,
                   email_html = ?,
                   markdown_text = ?,
                   intelligence_json = ?,
                   failed_repos = ?,
                   completed_at = ?,
                   progress_message = ?
               WHERE id = ?""",
            (
                status,
                slack_text,
                email_html,
                markdown_text,
                json.dumps(intelligence_json) if intelligence_json else None,
                json.dumps(failed_repos) if failed_repos else None,
                now,
                "Done" if status == "done" else ("Partial — some repos failed" if status == "partial" else "Failed"),
                job_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()
