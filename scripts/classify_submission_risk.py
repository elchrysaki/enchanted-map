from __future__ import annotations

import ipaddress
import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse, urlunparse

import requests


GITHUB_API = "https://api.github.com"
TOKEN = os.environ["GITHUB_TOKEN"]
REPOSITORY = os.environ["REPOSITORY"]
ISSUE_NUMBER = int(os.environ["ISSUE_NUMBER"])

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

MAX_BODY_LENGTH = 100_000
BOT_DUPLICATE_THRESHOLD = 3
HUMAN_DUPLICATE_THRESHOLD = 8
DUPLICATE_WINDOW_HOURS = 24

URL_PATTERN = re.compile(
    r"https?://[^\s<>()\[\]{}\"']+",
    flags=re.IGNORECASE,
)
DANGEROUS_SCHEME_PATTERN = re.compile(
    r"(?i)\b(?:file|javascript|data|vbscript):"
)
BLOCKED_HOST_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".home",
    ".lan",
)


def write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        print(f"{name}={value}")
        return
    with open(output_path, "a", encoding="utf-8") as output:
        output.write(f"{name}={value}\n")


def github_request(
    method: str,
    endpoint: str,
    *,
    expected_statuses: tuple[int, ...] = (200,),
    **kwargs: Any,
) -> requests.Response:
    response = requests.request(
        method,
        f"{GITHUB_API}{endpoint}",
        headers=HEADERS,
        timeout=45,
        **kwargs,
    )
    if response.status_code not in expected_statuses:
        raise RuntimeError(
            f"GitHub API request failed: {method} {endpoint} "
            f"returned {response.status_code}"
        )
    return response


def get_issue() -> dict[str, Any]:
    response = github_request(
        "GET",
        f"/repos/{REPOSITORY}/issues/{ISSUE_NUMBER}",
    )
    issue = response.json()
    if not isinstance(issue, dict) or issue.get("pull_request"):
        raise RuntimeError("The requested issue is unavailable.")
    return issue


def extract_urls(text: str) -> list[str]:
    return [match.rstrip(".,;:!?") for match in URL_PATTERN.findall(text)]


def normalized_url(value: str) -> str | None:
    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return None

    if parsed.scheme.lower() not in {"http", "https"}:
        return None
    if not parsed.hostname:
        return None

    hostname = parsed.hostname.rstrip(".").lower()
    netloc = hostname

    if parsed.port and parsed.port not in {80, 443}:
        netloc = f"{hostname}:{parsed.port}"

    path = re.sub(r"/+", "/", parsed.path or "/").rstrip("/") or "/"

    return urlunparse(
        (
            parsed.scheme.lower(),
            netloc,
            path,
            "",
            "",
            "",
        )
    )


def dangerous_url_reason(value: str) -> str | None:
    try:
        parsed = urlparse(value.strip())
        _ = parsed.port
    except ValueError:
        return "malformed-url"

    if parsed.username or parsed.password:
        return "embedded-credentials"

    hostname = (parsed.hostname or "").rstrip(".").lower()
    if not hostname:
        return None

    if hostname == "localhost" or hostname.endswith(BLOCKED_HOST_SUFFIXES):
        return "private-network-target"

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return None

    if not address.is_global:
        return "private-network-target"

    return None


def recent_issue_bodies(author: str) -> list[dict[str, Any]]:
    since = (
        datetime.now(timezone.utc)
        - timedelta(hours=DUPLICATE_WINDOW_HOURS)
    ).isoformat()

    try:
        response = github_request(
            "GET",
            f"/repos/{REPOSITORY}/issues",
            params={
                "state": "all",
                "creator": author,
                "since": since,
                "sort": "created",
                "direction": "desc",
                "per_page": 100,
            },
        )
    except (requests.RequestException, RuntimeError) as exc:
        print(f"::warning::Duplicate-spam check was skipped: {exc}")
        return []

    data = response.json()
    if not isinstance(data, list):
        return []

    return [
        item
        for item in data
        if isinstance(item, dict) and not item.get("pull_request")
    ]


def repeated_submission_is_severe(
    issue: dict[str, Any],
    current_urls: list[str],
) -> bool:
    user = issue.get("user")
    if not isinstance(user, dict):
        return False

    author = str(user.get("login") or "").strip()
    account_type = str(user.get("type") or "").strip().casefold()

    if not author:
        return False

    recent = recent_issue_bodies(author)
    if not recent:
        return False

    url_counts: Counter[str] = Counter()
    title_counts: Counter[str] = Counter()

    for item in recent:
        title = re.sub(
            r"\s+",
            " ",
            str(item.get("title") or "").strip().casefold(),
        )
        if title:
            title_counts[title] += 1

        body = str(item.get("body") or "")
        for url in extract_urls(body):
            normalized = normalized_url(url)
            if normalized:
                url_counts[normalized] += 1

    current_title = re.sub(
        r"\s+",
        " ",
        str(issue.get("title") or "").strip().casefold(),
    )
    normalized_current_urls = {
        value
        for value in (
            normalized_url(url)
            for url in current_urls
        )
        if value
    }

    threshold = (
        BOT_DUPLICATE_THRESHOLD
        if account_type == "bot"
        else HUMAN_DUPLICATE_THRESHOLD
    )

    repeated_url = any(
        url_counts[url] >= threshold
        for url in normalized_current_urls
    )
    repeated_title = (
        bool(current_title)
        and title_counts[current_title] >= threshold
    )

    return repeated_url or repeated_title


def classify(issue: dict[str, Any]) -> tuple[str, str]:
    body = str(issue.get("body") or "")

    if len(body) > MAX_BODY_LENGTH:
        return "security-rejected", "oversized-payload"

    if DANGEROUS_SCHEME_PATTERN.search(body):
        return "security-rejected", "dangerous-url-scheme"

    urls = extract_urls(body)

    for url in urls:
        reason = dangerous_url_reason(url)
        if reason:
            return "security-rejected", reason

    if repeated_submission_is_severe(issue, urls):
        return "security-rejected", "repeated-automated-spam"

    return "continue", "none"


def main() -> None:
    issue = get_issue()
    outcome, reason = classify(issue)

    write_output("risk_outcome", outcome)
    write_output("risk_reason_code", reason)

    if outcome == "security-rejected":
        print(
            "::warning title=Severe submission risk::"
            "The issue will be closed without website research."
        )
    else:
        print(
            "Preflight risk classification passed. "
            "The submission may continue to intake and research."
        )


if __name__ == "__main__":
    main()
