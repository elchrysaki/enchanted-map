from __future__ import annotations

import base64
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
import yaml


# ============================================================
# ENVIRONMENT
# ============================================================

GITHUB_API = "https://api.github.com"

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPOSITORY = os.environ["REPOSITORY"]
ISSUE_NUMBER = int(os.environ["ISSUE_NUMBER"])

OPPORTUNITY_FILE = Path(
    os.environ.get(
        "OPPORTUNITY_FILE",
        "",
    )
)

REVIEW_REPORT_FILE = Path(
    os.environ.get(
        "REVIEW_REPORT_FILE",
        f"artifacts/review-report-{ISSUE_NUMBER}.md",
    )
)

PUBLISHABLE_CONTENT_FILE = Path(
    os.environ.get(
        "PUBLISHABLE_CONTENT_FILE",
        os.environ.get(
            "AI_OUTPUT_FILE",
            f"artifacts/publishable-content-{ISSUE_NUMBER}.json",
        ),
    )
)

RAW_SUBMISSION_FILE = Path(
    os.environ.get(
        "RAW_SUBMISSION_FILE",
        f"artifacts/raw-submission-{ISSUE_NUMBER}.json",
    )
)

BASE_BRANCH_OVERRIDE = os.environ.get(
    "BASE_BRANCH",
    "",
).strip()

BRANCH_PREFIX = os.environ.get(
    "BRANCH_PREFIX",
    "automated-discovery",
).strip("/")

MAX_PR_BODY_LENGTH = 60_000
MAX_FILE_BYTES = 2_000_000

PR_COMMENT_MARKER = "<!-- enchanted-map-pr-created -->"
PR_BODY_MARKER = "<!-- enchanted-map-draft-pr -->"

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


# ============================================================
# BASIC HELPERS
# ============================================================

def fail(message: str) -> None:
    print(f"::error::{message}")
    raise SystemExit(1)


def warn(message: str) -> None:
    print(f"::warning::{message}")


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
        timeout=60,
        **kwargs,
    )

    if response.status_code not in expected_statuses:
        fail(
            "GitHub API request failed: "
            f"{method} {endpoint} returned "
            f"{response.status_code}\n"
            f"{response.text[:1500]}"
        )

    return response


def write_github_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")

    if not output_path:
        print(f"{name}={value}")
        return

    with open(output_path, "a", encoding="utf-8") as output:
        output.write(f"{name}={value}\n")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        fail(f"Required JSON file not found: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"Invalid JSON in {path}: {exc}")

    if not isinstance(data, dict):
        fail(f"Expected a JSON object in {path}")

    return data


def read_text_file(
    path: Path,
    *,
    maximum_bytes: int = MAX_FILE_BYTES,
) -> str:
    if not path.exists():
        fail(f"Required file not found: {path}")

    size = path.stat().st_size

    if size > maximum_bytes:
        fail(
            f"File is too large to commit safely: {path} "
            f"({size} bytes; maximum {maximum_bytes})"
        )

    return path.read_text(encoding="utf-8")


def neutralize_mentions(value: str) -> str:
    return value.replace("@", "@\u200b")


def sanitize_title(value: Any) -> str:
    text = str(value or "Untitled opportunity")
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return neutralize_mentions(text[:200])


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def parse_json_list_environment(
    name: str,
) -> list[str]:
    raw = os.environ.get(name, "").strip()

    if not raw:
        return []

    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        warn(
            f"{name} was not valid JSON. Reviewer assignment skipped."
        )
        return []

    if not isinstance(value, list):
        warn(
            f"{name} did not contain a JSON list. "
            "Reviewer assignment skipped."
        )
        return []

    result: list[str] = []
    seen: set[str] = set()

    for item in value:
        username = str(item).strip().lstrip("@")

        if not re.fullmatch(r"[A-Za-z0-9-]{1,39}", username):
            continue

        lowered = username.casefold()

        if lowered in seen:
            continue

        seen.add(lowered)
        result.append(username)

    return result[:15]


# ============================================================
# REPOSITORY AND BRANCH HELPERS
# ============================================================

def get_repository() -> dict[str, Any]:
    response = github_request(
        "GET",
        f"/repos/{REPOSITORY}",
    )

    data = response.json()

    if not isinstance(data, dict):
        fail("GitHub returned an invalid repository object.")

    return data


def get_default_branch(repository: dict[str, Any]) -> str:
    if BASE_BRANCH_OVERRIDE:
        return BASE_BRANCH_OVERRIDE

    default_branch = repository.get("default_branch")

    if not isinstance(default_branch, str) or not default_branch:
        fail("Could not determine the repository default branch.")

    return default_branch


def get_branch_sha(branch: str) -> str | None:
    encoded_branch = quote(
        branch,
        safe="",
    )

    response = requests.get(
        f"{GITHUB_API}/repos/{REPOSITORY}/git/ref/heads/{encoded_branch}",
        headers=HEADERS,
        timeout=60,
    )

    if response.status_code == 404:
        return None

    if response.status_code != 200:
        fail(
            f"Could not inspect branch '{branch}': "
            f"{response.status_code} {response.text[:1000]}"
        )

    data = response.json()

    try:
        return str(data["object"]["sha"])
    except (KeyError, TypeError):
        fail(f"GitHub returned an invalid ref for branch '{branch}'.")

    return None


def create_branch(
    branch: str,
    base_sha: str,
) -> None:
    github_request(
        "POST",
        f"/repos/{REPOSITORY}/git/refs",
        expected_statuses=(201,),
        json={
            "ref": f"refs/heads/{branch}",
            "sha": base_sha,
        },
    )


def ensure_branch(
    branch: str,
    base_branch: str,
) -> None:
    existing_sha = get_branch_sha(branch)

    if existing_sha:
        print(
            f"Reusing existing branch: {branch}"
        )
        return

    base_sha = get_branch_sha(base_branch)

    if not base_sha:
        fail(
            f"Base branch was not found: {base_branch}"
        )

    create_branch(
        branch,
        base_sha,
    )

    print(
        f"Created branch: {branch}"
    )


# ============================================================
# FILE COMMITTING
# ============================================================

def repository_path(path: Path) -> str:
    if path.is_absolute():
        fail(
            "OPPORTUNITY_FILE must be a repository-relative path."
        )

    normalized = path.as_posix().lstrip("/")

    if (
        not normalized
        or normalized.startswith("../")
        or "/../" in normalized
    ):
        fail(
            f"Unsafe repository path: {path}"
        )

    if not normalized.startswith("opportunities/"):
        fail(
            "Generated opportunity pages must be stored "
            "under the opportunities/ directory."
        )

    return normalized


def get_file_sha(
    path: str,
    branch: str,
) -> str | None:
    encoded_path = quote(
        path,
        safe="/",
    )

    response = requests.get(
        f"{GITHUB_API}/repos/{REPOSITORY}/contents/{encoded_path}",
        headers=HEADERS,
        params={
            "ref": branch,
        },
        timeout=60,
    )

    if response.status_code == 404:
        return None

    if response.status_code != 200:
        fail(
            f"Could not inspect '{path}' on '{branch}': "
            f"{response.status_code} {response.text[:1000]}"
        )

    data = response.json()

    if not isinstance(data, dict):
        fail(
            f"GitHub returned invalid file metadata for '{path}'."
        )

    sha = data.get("sha")

    if not isinstance(sha, str):
        fail(
            f"GitHub returned no file SHA for '{path}'."
        )

    return sha


def put_file(
    path: str,
    content: str,
    branch: str,
    commit_message: str,
) -> None:
    existing_sha = get_file_sha(
        path,
        branch,
    )

    payload: dict[str, Any] = {
        "message": commit_message,
        "content": base64.b64encode(
            content.encode("utf-8")
        ).decode("ascii"),
        "branch": branch,
    }

    if existing_sha:
        payload["sha"] = existing_sha

    expected_statuses = (
        (200,)
        if existing_sha
        else (201,)
    )

    github_request(
        "PUT",
        f"/repos/{REPOSITORY}/contents/{quote(path, safe='/')}",
        expected_statuses=expected_statuses,
        json=payload,
    )

    action = (
        "Updated"
        if existing_sha
        else "Created"
    )

    print(
        f"{action} repository file: {path}"
    )


# ============================================================
# PULL REQUEST HELPERS
# ============================================================

def get_existing_pull_request(
    owner: str,
    branch: str,
) -> dict[str, Any] | None:
    response = github_request(
        "GET",
        f"/repos/{REPOSITORY}/pulls",
        params={
            "state": "open",
            "head": f"{owner}:{branch}",
            "per_page": 10,
        },
    )

    pulls = response.json()

    if not isinstance(pulls, list):
        fail("GitHub returned an invalid pull-request list.")

    for pull in pulls:
        if isinstance(pull, dict):
            return pull

    return None


def build_pull_request_body(
    report: str,
    issue_url: str | None,
    opportunity_path: str,
) -> str:
    header = [
        PR_BODY_MARKER,
        "## ðºï¸ Automated Quest Draft",
        "",
        (
            f"This draft was generated from issue "
            f"#{ISSUE_NUMBER}. It must be reviewed and edited "
            "by a human before merging."
        ),
        "",
        f"**Proposed page:** `{opportunity_path}`",
    ]

    if issue_url:
        header.extend(
            [
                "",
                f"**Original submission:** {issue_url}",
            ]
        )

    header.extend(
        [
            "",
            "---",
            "",
        ]
    )

    body = "\n".join(header) + report

    if len(body) > MAX_PR_BODY_LENGTH:
        warn(
            "The review report exceeded the pull-request body "
            "limit and was truncated."
        )

        body = (
            body[: MAX_PR_BODY_LENGTH - 200]
            + "\n\n---\n\n"
            + "The report was truncated. Review the workflow artifact "
            + f"`{REVIEW_REPORT_FILE.name}` for the complete copy.\n"
        )

    return body


def create_pull_request(
    title: str,
    body: str,
    branch: str,
    base_branch: str,
) -> dict[str, Any]:
    response = github_request(
        "POST",
        f"/repos/{REPOSITORY}/pulls",
        expected_statuses=(201,),
        json={
            "title": title,
            "body": body,
            "head": branch,
            "base": base_branch,
            "draft": True,
            "maintainer_can_modify": True,
        },
    )

    data = response.json()

    if not isinstance(data, dict):
        fail("GitHub returned an invalid pull-request object.")

    return data


def update_pull_request(
    pull_number: int,
    title: str,
    body: str,
) -> dict[str, Any]:
    response = github_request(
        "PATCH",
        f"/repos/{REPOSITORY}/pulls/{pull_number}",
        json={
            "title": title,
            "body": body,
        },
    )

    data = response.json()

    if not isinstance(data, dict):
        fail("GitHub returned an invalid updated pull request.")

    return data


def ensure_label(
    name: str,
    color: str,
    description: str,
) -> None:
    encoded_name = quote(
        name,
        safe="",
    )

    response = requests.get(
        f"{GITHUB_API}/repos/{REPOSITORY}/labels/{encoded_name}",
        headers=HEADERS,
        timeout=60,
    )

    if response.status_code == 200:
        return

    if response.status_code != 404:
        fail(
            f"Could not inspect label '{name}': "
            f"{response.status_code} {response.text[:800]}"
        )

    github_request(
        "POST",
        f"/repos/{REPOSITORY}/labels",
        expected_statuses=(201,),
        json={
            "name": name,
            "color": color,
            "description": description,
        },
    )


def add_labels_to_pull_request(
    pull_number: int,
    labels: list[str],
) -> None:
    github_request(
        "POST",
        f"/repos/{REPOSITORY}/issues/{pull_number}/labels",
        json={
            "labels": labels,
        },
    )


def request_reviewers(
    pull_number: int,
    reviewers: list[str],
) -> None:
    if not reviewers:
        return

    response = requests.post(
        (
            f"{GITHUB_API}/repos/{REPOSITORY}/pulls/"
            f"{pull_number}/requested_reviewers"
        ),
        headers=HEADERS,
        json={
            "reviewers": reviewers,
        },
        timeout=60,
    )

    if response.status_code == 201:
        print(
            "Requested reviewers: "
            + ", ".join(reviewers)
        )
        return

    if response.status_code in {403, 404, 422}:
        warn(
            "GitHub could not request one or more reviewers. "
            "The PR was still created successfully. Confirm that "
            "the usernames are repository collaborators."
        )
        return

    fail(
        "Could not request reviewers: "
        f"{response.status_code} {response.text[:1000]}"
    )


# ============================================================
# ORIGINAL ISSUE UPDATE
# ============================================================

def comment_exists() -> bool:
    response = github_request(
        "GET",
        f"/repos/{REPOSITORY}/issues/{ISSUE_NUMBER}/comments",
        params={
            "per_page": 100,
        },
    )

    comments = response.json()

    if not isinstance(comments, list):
        return False

    return any(
        PR_COMMENT_MARKER
        in str(comment.get("body", ""))
        for comment in comments
        if isinstance(comment, dict)
    )


def comment_on_issue(
    pull_url: str,
) -> None:
    if comment_exists():
        print(
            "Pull-request issue comment already exists. "
            "Skipping duplicate."
        )
        return

    body = "\n".join(
        [
            PR_COMMENT_MARKER,
            "## â¨ A Draft Quest Is Ready",
            "",
            (
                "The researched and formatted opportunity has "
                "been placed in a draft pull request for human review."
            ),
            "",
            f"ð {pull_url}",
            "",
            (
                "A moderator may edit, request changes, reject, "
                "or merge the draft."
            ),
        ]
    )

    github_request(
        "POST",
        f"/repos/{REPOSITORY}/issues/{ISSUE_NUMBER}/comments",
        expected_statuses=(201,),
        json={
            "body": body,
        },
    )


def add_labels_to_issue(
    labels: list[str],
) -> None:
    github_request(
        "POST",
        f"/repos/{REPOSITORY}/issues/{ISSUE_NUMBER}/labels",
        json={
            "labels": labels,
        },
    )


# ============================================================
# INPUT METADATA
# ============================================================

def get_publishable_metadata() -> tuple[str, str, bool]:
    data = read_json(
        PUBLISHABLE_CONTENT_FILE
    )

    if (
        data.get("record_type")
        != "publishable-opportunity-draft"
    ):
        fail(
            "PUBLISHABLE_CONTENT_FILE is not a "
            "publishable-opportunity-draft record."
        )

    identity = data.get("identity", {})

    if not isinstance(identity, dict):
        identity = {}

    moderation = data.get("moderation", {})

    if not isinstance(moderation, dict):
        moderation = {}

    title = sanitize_title(
        identity.get("title")
    )

    action = str(
        moderation.get(
            "recommended_action",
            "hold-for-human-review",
        )
    )

    safe_to_generate = bool(
        moderation.get(
            "safe_to_generate_draft_page",
            False,
        )
    )

    return title, action, safe_to_generate


def get_issue_url() -> str | None:
    if not RAW_SUBMISSION_FILE.exists():
        return None

    data = read_json(
        RAW_SUBMISSION_FILE
    )

    issue = data.get("issue", {})

    if not isinstance(issue, dict):
        return None

    value = issue.get("url")

    if not isinstance(value, str):
        return None

    if not value.startswith(
        f"https://github.com/{REPOSITORY}/issues/"
    ):
        return None

    return value


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    if not str(OPPORTUNITY_FILE):
        fail(
            "OPPORTUNITY_FILE was not provided."
        )

    opportunity_path = repository_path(
        OPPORTUNITY_FILE
    )

    opportunity_content = read_text_file(
        OPPORTUNITY_FILE
    )

    review_report = read_text_file(
        REVIEW_REPORT_FILE
    )

    title, formatter_action, safe_to_generate = (
        get_publishable_metadata()
    )

    repository = get_repository()
    owner = repository.get("owner", {}).get("login")

    if not isinstance(owner, str) or not owner:
        fail("Could not determine the repository owner.")

    base_branch = get_default_branch(
        repository
    )

    file_slug = slugify(
        OPPORTUNITY_FILE.stem
    ) or f"opportunity-{ISSUE_NUMBER}"

    branch = (
        f"{BRANCH_PREFIX}/issue-{ISSUE_NUMBER}-{file_slug}"
    )[:240].rstrip("-/")

    ensure_branch(
        branch,
        base_branch,
    )

    put_file(
        opportunity_path,
        opportunity_content,
        branch,
        (
            f"Add {title} opportunity draft "
            f"(issue #{ISSUE_NUMBER})"
        ),
    )

    issue_url = get_issue_url()

    pr_body = build_pull_request_body(
        review_report,
        issue_url,
        opportunity_path,
    )

    pr_title = (
        f"ðºï¸ Quest Review: {title}"
    )[:250]

    existing_pull = get_existing_pull_request(
        owner,
        branch,
    )

    if existing_pull:
        pull_number = int(
            existing_pull["number"]
        )

        pull = update_pull_request(
            pull_number,
            pr_title,
            pr_body,
        )

        print(
            f"Updated existing draft PR #{pull_number}."
        )
    else:
        pull = create_pull_request(
            pr_title,
            pr_body,
            branch,
            base_branch,
        )

        pull_number = int(
            pull["number"]
        )

        print(
            f"Created draft PR #{pull_number}."
        )

    pull_url = str(
        pull.get("html_url") or ""
    )

    if not pull_url:
        fail(
            "GitHub returned no pull-request URL."
        )

    ensure_label(
        "generated-discovery",
        "8B5CF6",
        "An opportunity page generated from a community submission.",
    )

    ensure_label(
        "needs-maintainer-review",
        "F4C542",
        "Requires human review before merging.",
    )

    pull_labels = [
        "generated-discovery",
        "needs-maintainer-review",
    ]

    if not safe_to_generate:
        ensure_label(
            "ai-needs-attention",
            "D73A4A",
            "The AI formatter marked the draft as unsafe or incomplete.",
        )

        pull_labels.append(
            "ai-needs-attention"
        )

    add_labels_to_pull_request(
        pull_number,
        pull_labels,
    )

    reviewers = parse_json_list_environment(
        "MODERATORS"
    )

    request_reviewers(
        pull_number,
        reviewers,
    )

    ensure_label(
        "pull-request-created",
        "0E8A16",
        "A draft pull request has been created for this submission.",
    )

    add_labels_to_issue(
        [
            "pull-request-created",
        ]
    )

    comment_on_issue(
        pull_url,
    )

    write_github_output(
        "pull_request_number",
        str(pull_number),
    )

    write_github_output(
        "pull_request_url",
        pull_url,
    )

    write_github_output(
        "branch_name",
        branch,
    )

    write_github_output(
        "base_branch",
        base_branch,
    )

    write_github_output(
        "formatter_recommended_action",
        formatter_action,
    )

    print(
        f"Draft pull request: {pull_url}"
    )
    print(
        f"Branch: {branch}"
    )
    print(
        f"Base branch: {base_branch}"
    )


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as exc:
        fail(
            f"Network request failed: {exc}"
        )
    except KeyboardInterrupt:
        sys.exit(130)
