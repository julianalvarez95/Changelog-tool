"""
Job API routes: trigger pipeline execution and poll job status.

POST /jobs                  — create a job and start the pipeline in background
GET  /jobs/{job_id}         — poll job status and progress
GET  /jobs/{job_id}/result  — retrieve rendered output for a completed job
POST /jobs/{job_id}/send    — send rendered output to selected distribution targets
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from web.db import create_job, get_db, get_job, list_jobs
from web.tasks import run_pipeline

router = APIRouter(prefix="/jobs", tags=["jobs"])

VALID_TONES = {"business", "technical", "executive"}


class JobRequest(BaseModel):
    since: str                    # "YYYY-MM-DD"
    until: str                    # "YYYY-MM-DD"
    tone: Optional[str] = None    # overrides config.changelog.tone for this job


class SendRequest(BaseModel):
    targets: list[str]  # subset of ["slack", "email"]


@router.get("")
def list_jobs_endpoint():
    """List all changelog jobs, newest first. Excludes rendered content (use /result for that)."""
    jobs = list_jobs(limit=100)
    return {"jobs": jobs}


@router.post("", status_code=202)
def create_job_endpoint(
    params: JobRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
):
    """Trigger changelog generation. Returns job_id immediately (non-blocking)."""
    # Validate date formats and ordering
    try:
        since_dt = datetime.strptime(params.since, "%Y-%m-%d")
        until_dt = datetime.strptime(params.until, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail="since and until must be YYYY-MM-DD format")

    if since_dt >= until_dt:
        raise HTTPException(status_code=400, detail="since must be before until")

    if params.tone is not None and params.tone not in VALID_TONES:
        raise HTTPException(status_code=422, detail=f"tone must be one of: {', '.join(sorted(VALID_TONES))}")

    job_id = create_job(params.since, params.until)
    background_tasks.add_task(run_pipeline, job_id, params.since, params.until, params.tone)
    return {"job_id": job_id, "status": "queued"}


@router.get("/{job_id}")
def get_job_endpoint(job_id: str, db=Depends(get_db)):
    """Poll job status and progress message."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Return only status fields — rendered content excluded from this endpoint
    # (use GET /jobs/{job_id}/result to retrieve slack_text/email_html/markdown_text)
    return {
        "id": job["id"],
        "status": job["status"],
        "progress_message": job["progress_message"],
        "since": job["since"],
        "until": job["until"],
        "failed_repos": job["failed_repos"],
        "created_at": job["created_at"],
        "completed_at": job["completed_at"],
    }


@router.get("/{job_id}/result")
def get_job_result_endpoint(job_id: str, db=Depends(get_db)):
    """Retrieve rendered changelog output for a completed job.

    Returns slack_text, email_html, and markdown_text.
    Use GET /jobs/{job_id} to poll status before calling this endpoint.
    """
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Only "done" and "partial" jobs have rendered output
    if job["status"] not in ("done", "partial"):
        raise HTTPException(
            status_code=409,
            detail=f"Job not complete (status={job['status']})",
        )

    return {
        "id": job["id"],
        "status": job["status"],
        "slack_text": job["slack_text"],
        "email_html": job["email_html"],
        "markdown_text": job["markdown_text"],
        "failed_repos": job["failed_repos"],
        "completed_at": job["completed_at"],
    }


@router.post("/{job_id}/send")
def send_job_endpoint(job_id: str, params: SendRequest):
    """Send rendered changelog to selected distribution targets.

    Reads rendered output from SQLite (stored by the pipeline).
    Returns per-target result: {"slack": {"success": bool, "error": str|null}, ...}
    """
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] not in ("done", "partial"):
        raise HTTPException(
            status_code=409,
            detail=f"Job not complete (status={job['status']})",
        )

    valid_targets = {"slack", "email"}
    unknown = set(params.targets) - valid_targets
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown targets: {', '.join(sorted(unknown))}")

    if not params.targets:
        raise HTTPException(status_code=422, detail="targets must not be empty")

    from src.config import load_config

    config = load_config()
    env = config["_env"]
    dist_cfg = config.get("distribution", {})
    changelog_cfg = config.get("changelog", {})

    results: dict[str, dict] = {}

    if "slack" in params.targets:
        slack_cfg = dist_cfg.get("slack", {})
        if not slack_cfg:
            results["slack"] = {"success": False, "error": "No Slack distribution config found"}
        else:
            from src.distributors.slack import send as slack_send
            channel = slack_cfg.get("channel", "#general")
            try:
                ok = slack_send(token=env.get("slack_bot_token", ""), channel=channel, text=job["slack_text"])
                results["slack"] = {"success": ok, "error": None if ok else "Slack API returned failure"}
            except Exception as exc:
                results["slack"] = {"success": False, "error": str(exc)}

    if "email" in params.targets:
        email_cfg = dist_cfg.get("email", {})
        if not email_cfg:
            results["email"] = {"success": False, "error": "No email distribution config found"}
        else:
            from src.distributors.email import send as email_send
            since_str = job["since"]
            until_str = job["until"]
            try:
                since_dt = datetime.strptime(since_str, "%Y-%m-%d")
                until_dt = datetime.strptime(until_str, "%Y-%m-%d")
                period_label = f"{since_dt.strftime('%-d %b')} — {until_dt.strftime('%-d %b %Y')}"
            except ValueError:
                period_label = f"{since_str} — {until_str}"

            subject_template = email_cfg.get("subject", "Changelog {title} - {period}")
            subject = subject_template.format(
                title=changelog_cfg.get("title", "Changelog"),
                period=period_label,
            )
            try:
                ok = email_send(
                    gmail_address=env.get("gmail_address", ""),
                    app_password=env.get("gmail_app_password", ""),
                    recipients=email_cfg.get("recipients", []),
                    subject=subject,
                    html_body=job["email_html"],
                    from_name=email_cfg.get("from_name", "Changelog Bot"),
                )
                results["email"] = {"success": ok, "error": None if ok else "Email send returned failure"}
            except Exception as exc:
                results["email"] = {"success": False, "error": str(exc)}

    return {"job_id": job_id, "results": results}
