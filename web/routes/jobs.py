"""
Job API routes: trigger pipeline execution and poll job status.

POST /jobs              — create a job and start the pipeline in background
GET  /jobs/{job_id}     — poll job status and progress
GET  /jobs/{job_id}/result — retrieve rendered output for a completed job
"""
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from web.db import create_job, get_db, get_job
from web.tasks import run_pipeline

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobRequest(BaseModel):
    since: str  # "YYYY-MM-DD"
    until: str  # "YYYY-MM-DD"


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

    job_id = create_job(params.since, params.until)
    background_tasks.add_task(run_pipeline, job_id, params.since, params.until)
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
