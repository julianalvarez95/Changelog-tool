"""
Fetch commits from Bitbucket Cloud REST API v2.
"""
import sys
from datetime import datetime
from typing import Optional

import requests


BITBUCKET_API = "https://api.bitbucket.org/2.0"


def fetch_commits(
    api_token: str,
    workspace: str,
    repo: str,
    branch: str = "main",
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> list[dict]:
    """
    Fetch commits from a Bitbucket Cloud repo.
    Returns list of dicts: {sha, message, url, author, date}

    Auth: Bitbucket HTTP access tokens (created in Bitbucket workspace settings)
    use Bearer auth. These are different from Atlassian API tokens (id.atlassian.com).
    """
    if not api_token:
        print(
            f"[ERROR] BITBUCKET_API_TOKEN is required "
            f"to fetch from {workspace}/{repo}",
            file=sys.stderr,
        )
        return []

    headers = {"Authorization": f"Bearer {api_token}"}
    url = f"{BITBUCKET_API}/repositories/{workspace}/{repo}/commits/{branch}"
    result = []

    try:
        while url:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code == 401:
                print(
                    f"[ERROR] Bitbucket auth failed for {workspace}/{repo}. "
                    "Check BITBUCKET_API_TOKEN.",
                    file=sys.stderr,
                )
                return []
            if resp.status_code != 200:
                print(
                    f"[ERROR] Bitbucket API returned {resp.status_code} for {workspace}/{repo}",
                    file=sys.stderr,
                )
                return []

            data = resp.json()
            page_commits = data.get("values", [])
            stop = False

            for c in page_commits:
                date_str = c.get("date", "")
                commit_dt = _parse_iso(date_str)

                # Stop if we've gone past the 'since' window
                if since and commit_dt and commit_dt < since.replace(tzinfo=None):
                    stop = True
                    break

                # Skip commits after 'until'
                if until and commit_dt and commit_dt > until.replace(tzinfo=None):
                    continue

                author_raw = c.get("author", {})
                author_name = author_raw.get("user", {}).get("display_name") or author_raw.get("raw", "Unknown")

                result.append({
                    "sha": c.get("hash", "")[:8],
                    "message": c.get("message", "").strip(),
                    "url": c.get("links", {}).get("html", {}).get("href"),
                    "author": author_name,
                    "date": date_str,
                })

            if stop:
                break

            url = data.get("next")  # pagination

        print(f"[bitbucket] Fetched {len(result)} commits from {workspace}/{repo}@{branch}")
        return result

    except requests.RequestException as e:
        print(f"[ERROR] Network error fetching from Bitbucket ({workspace}/{repo}): {e}", file=sys.stderr)
        return []


def _parse_iso(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        # Bitbucket returns ISO 8601 with timezone offset
        from datetime import timezone
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None
