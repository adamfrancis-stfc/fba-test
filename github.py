import os
import sys
import subprocess
from datetime import datetime

import requests

class PR:
    def __init__(self, number: int, author: str, title: str, body: str, branch: str, url: str, created_at: datetime):
        self.number = number
        self.author = author
        self.title = title
        self.body = body
        self.branch = branch
        self.url = url
        self.created_at = created_at

    @staticmethod
    def from_gh_response(pr: dict):
        return PR(
            int(pr["number"]),
            pr["user"]["login"],
            pr["title"],
            pr["body"],
            pr["head"]["ref"],
            pr["html_url"],
            datetime.strptime(pr["created_at"], "%Y-%m-%dT%H:%M:%SZ")
        )

def get_github_token() -> str | None:
    if token := os.environ.get("GITHUB_TOKEN"):
        return token

    try:
        result = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1] or None
    except (subprocess.SubprocessError, OSError):
        pass

    return None

def get_repo_prs(repo: str) -> list[PR]:
    """Fetch PRs for a repo via the GitHub REST API."""
    headers = {"Accept": "application/vnd.github+json"}
    if token := get_github_token():
        headers["Authorization"] = f"Bearer {token}"

    prs = []
    url = f"https://api.github.com/repos/{repo}/pulls"
    params = {"state": "open", "per_page": 100}

    while url:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code == 401:
            sys.exit("Error: GitHub rejected the credentials. Set GITHUB_TOKEN or check git's stored credentials.")
        if resp.status_code == 404:
            sys.exit(f"Error: repo '{repo}' not found (or you lack access).")
        resp.raise_for_status()

        prs.extend(resp.json())
        url = resp.links.get("next", {}).get("url")
        params = None  # subsequent requests use the full URL already

    return [PR.from_gh_response(pr) for pr in prs]
