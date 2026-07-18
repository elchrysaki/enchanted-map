from __future__ import annotations

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

PR_COMMENT_MARKER = "<!-- offmap-pr-created -->"
LEGACY_PR_COMMENT_MARKER = (
    "<!-- enchanted-map-pr-created -->"
)
PR_BODY_MARKER = "<!-- offmap-draft-pr -->"

ALLOWED_MAIN_CATEGORIES = {
    "events",
    "internships",
    "competitions",
    "research",
    "fellowships",
    "scholarships",
    "courses",
    "innovation",
    "creative-calls",
    "exchanges",
    "volunteering",
    "other",
}

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


def write_github_output(
    name: str,
    value: str,
) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")

    if not output_path:
        print(f"{name}={value}")
        return

    with open(
        output_path,
        "a",
        encoding="utf-8",
    ) as output:
        output.write(f"{name}={value}\n")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        fail(f"Required JSON file not found: {path}")

    try:
        data = json.loads(
            path.read_text(encoding="utf-8")
        )
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

    if path.is_symlink():
        fail(
            "Required file must not be a symbolic link: "
            f"{path}"
        )

    size = path.stat().st_size

    if size > maximum_bytes:
        fail(
            f"File is too large to commit safely: {path} "
            f"({size} bytes; maximum {maximum_bytes})"
        )

    try:
        return path.read_text(
            encoding="utf-8"
        )
    except UnicodeDecodeError as exc:
        fail(
            f"File is not valid UTF-8: {path}: {exc}"
        )


def require_object(
    parent: dict[str, Any],
    key: str,
    *,
    context: str,
) -> dict[str, Any]:
    value = parent.get(key)

    if not isinstance(value, dict):
        fail(
            f"{context}: '{key}' must be an object."
        )

    return value


def require_string(
    parent: dict[str, Any],
    key: str,
    *,
    context: str,
) -> str:
    value = parent.get(key)

    if (
        not isinstance(value, str)
        or not value.strip()
    ):
        fail(
            f"{context}: '{key}' must contain text."
        )

    return value.strip()


def neutralize_mentions(value: str) -> str:
    return value.replace(
        "@",
        "@\u200b",
    )


def sanitize_title(value: str) -> str:
    text = re.sub(
        r"[\r\n\t]+",
        " ",
        value,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    if not text:
        fail(
            "Opportunity title must not be empty."
        )

    return neutralize_mentions(
        text[:200]
    )


def parse_json_list_environment(
    name: str,
) -> list[str]:
    raw = os.environ.get(
        name,
        "",
    ).strip()

    if not raw:
        return []

    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        warn(
            f"{name} was not valid JSON. "
            "Reviewer assignment skipped."
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
        username = (
            str(item)
            .strip()
            .lstrip("@")
        )

        if not re.fullmatch(
            r"[A-Za-z0-9-]{1,39}",
            username,
        ):
            continue

        lowered = username.casefold()

        if lowered in seen:
            continue

        seen.add(lowered)
        result.append(username)

    return result[:15]


def validate_environment() -> None:
    if ISSUE_NUMBER <= 0:
        fail(
            "ISSUE_NUMBER must be a positive integer."
        )

    if not re.fullmatch(
        r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",
        REPOSITORY,
    ):
        fail(
            "REPOSITORY must use the form owner/name."
        )

    if not BRANCH_PREFIX:
        fail(
            "BRANCH_PREFIX must not be empty."
        )

    if not re.fullmatch(
        r"[A-Za-z0-9._/-]+",
        BRANCH_PREFIX,
    ):
        fail(
            "BRANCH_PREFIX contains unsupported characters."
        )


# ============================================================
# SCHEMA-V2 INPUT VALIDATION
# ============================================================

def get_publishable_metadata() -> dict[str, str]:
    data = read_json(
        PUBLISHABLE_CONTENT_FILE
    )

    if data.get("schema_version") != 2:
        fail(
            "PUBLISHABLE_CONTENT_FILE must use "
            "schema version 2."
        )

    if (
        data.get("record_type")
        != "publishable-opportunity-draft"
    ):
        fail(
            "PUBLISHABLE_CONTENT_FILE is not a "
            "publishable-opportunity-draft record."
        )

    if data.get("issue_number") != ISSUE_NUMBER:
        fail(
            "Publishable issue_number does not match "
            "ISSUE_NUMBER."
        )

    identity = require_object(
        data,
        "identity",
        context="Publishable content",
    )

    moderation = require_object(
        data,
        "moderation",
        context="Publishable content",
    )

    title = require_string(
        identity,
        "title",
        context="Publishable identity",
    )

    main_category = require_string(
        identity,
        "main_category",
        context="Publishable identity",
    )

    category = require_string(
        identity,
        "category",
        context="Publishable identity",
    )

    if (
        main_category
        not in ALLOWED_MAIN_CATEGORIES
    ):
        fail(
            f"Invalid main category: {main_category}"
        )

    if (
        moderation.get("human_review_required")
        is not True
    ):
        fail(
            "Publishable draft must preserve "
            "human_review_required: true."
        )

    if (
        moderation.get(
            "safe_to_generate_draft_page"
        )
        is not True
    ):
        fail(
            "Publishable draft was not marked safe "
            "to generate."
        )

    action = moderation.get(
        "recommended_action"
    )

    if action != "continue-to-draft-pr":
        fail(
            "Publishable draft must recommend "
            "'continue-to-draft-pr'."
        )

    return {
        "title": sanitize_title(title),
        "main_category": main_category,
        "category": category,
        "formatter_action": action,
    }


def repository_path(
    path: Path,
    metadata: dict[str, str],
) -> str:
    if not str(path):
        fail(
            "OPPORTUNITY_FILE was not provided."
        )

    if path.is_absolute():
        fail(
            "OPPORTUNITY_FILE must be a "
            "repository-relative path."
        )

    normalized = path.as_posix()

    if (
        not normalized
        or normalized.startswith("../")
        or "/../" in normalized
        or normalized.startswith("/")
    ):
        fail(
            f"Unsafe repository path: {path}"
        )

    expected_directory = (
        "opportunities/"
        f"{metadata['main_category']}"
    )

    if (
        path.parent.as_posix()
        != expected_directory
    ):
        fail(
            "Generated opportunity path must use "
            "opportunities/<main_category>/<slug>.md."
        )

    if path.suffix != ".md":
        fail(
            "Generated opportunity file must use .md."
        )

    if not re.fullmatch(
        r"[a-z0-9]+(?:-[a-z0-9]+)*",
        path.stem,
    ):
        fail(
            "Generated opportunity filename must be "
            "a lowercase hyphenated slug."
        )

    return normalized


def validate_opportunity_file(
    content: str,
    opportunity_path: str,
    metadata: dict[str, str],
) -> None:
    match = re.match(
        r"\A---\s*\n(.*?)\n---\s*(?:\n|$)",
        content,
        flags=re.DOTALL,
    )

    if not match:
        fail(
            "Generated opportunity file does not begin "
            "with YAML front matter."
        )

    try:
        front_matter = yaml.safe_load(
            match.group(1)
        )
    except yaml.YAMLError as exc:
        fail(
            "Generated opportunity file contains "
            f"invalid YAML: {exc}"
        )

    if not isinstance(front_matter, dict):
        fail(
            "Generated opportunity front matter "
            "must be an object."
        )

    if (
        front_matter.get("schema_version")
        != 2
    ):
        fail(
            "Generated opportunity file must use "
            "schema version 2."
        )

    if (
        front_matter.get("record_type")
        != "opportunity"
    ):
        fail(
            "Generated opportunity record_type must "
            "be 'opportunity'."
        )

    if (
        front_matter.get("status")
        != "pending-review"
    ):
        fail(
            "Generated opportunity must have "
            "status 'pending-review'."
        )

    if (
        front_matter.get("main_category")
        != metadata["main_category"]
    ):
        fail(
            "Generated opportunity main_category "
            "does not match the publishable record."
        )

    if (
        front_matter.get("category")
        != metadata["category"]
    ):
        fail(
            "Generated opportunity category does not "
            "match the publishable record."
        )

    path = Path(
        opportunity_path
    )

    if (
        front_matter.get("slug")
        != path.stem
    ):
        fail(
            "Generated opportunity slug does not "
            "match its filename."
        )

    submission = require_object(
        front_matter,
        "submission",
        context="Generated opportunity",
    )

    if (
        submission.get("issue_number")
        != ISSUE_NUMBER
    ):
        fail(
            "Generated opportunity submission issue "
            "does not match ISSUE_NUMBER."
        )


# ============================================================
# REPOSITORY AND SINGLE-FILE BRANCH HELPERS
# ============================================================

def get_repository() -> dict[str, Any]:
    data = github_request(
        "GET",
        f"/repos/{REPOSITORY}",
    ).json()

    if not isinstance(data, dict):
        fail(
            "GitHub returned an invalid "
            "repository object."
        )

    return data


def get_default_branch(
    repository: dict[str, Any],
) -> str:
    if BASE_BRANCH_OVERRIDE:
        return BASE_BRANCH_OVERRIDE

    default_branch = repository.get(
        "default_branch"
    )

    if (
        not isinstance(default_branch, str)
        or not default_branch
    ):
        fail(
            "Could not determine the repository "
            "default branch."
        )

    return default_branch


def get_branch_sha(
    branch: str,
) -> str | None:
    encoded_branch = quote(
        branch,
        safe="",
    )

    response = requests.get(
        (
            f"{GITHUB_API}/repos/{REPOSITORY}/"
            f"git/ref/heads/{encoded_branch}"
        ),
        headers=HEADERS,
        timeout=60,
    )

    if response.status_code == 404:
        return None

    if response.status_code != 200:
        fail(
            f"Could not inspect branch '{branch}': "
            f"{response.status_code} "
            f"{response.text[:1000]}"
        )

    data = response.json()

    try:
        return str(
            data["object"]["sha"]
        )
    except (
        KeyError,
        TypeError,
    ):
        fail(
            "GitHub returned an invalid ref for "
            f"branch '{branch}'."
        )

    return None


def create_single_file_branch_commit(
    branch: str,
    base_branch: str,
    path: str,
    content: str,
    commit_message: str,
) -> None:
    base_sha = get_branch_sha(
        base_branch
    )

    if not base_sha:
        fail(
            f"Base branch was not found: {base_branch}"
        )

    commit_data = github_request(
        "GET",
        (
            f"/repos/{REPOSITORY}/git/commits/"
            f"{base_sha}"
        ),
    ).json()

    try:
        base_tree_sha = str(
            commit_data["tree"]["sha"]
        )
    except (
        KeyError,
        TypeError,
    ):
        fail(
            "GitHub returned an invalid base commit."
        )

    blob_data = github_request(
        "POST",
        f"/repos/{REPOSITORY}/git/blobs",
        expected_statuses=(201,),
        json={
            "content": content,
            "encoding": "utf-8",
        },
    ).json()

    blob_sha = blob_data.get(
        "sha"
    )

    if not isinstance(blob_sha, str):
        fail(
            "GitHub returned an invalid blob."
        )

    tree_data = github_request(
        "POST",
        f"/repos/{REPOSITORY}/git/trees",
        expected_statuses=(201,),
        json={
            "base_tree": base_tree_sha,
            "tree": [
                {
                    "path": path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob_sha,
                }
            ],
        },
    ).json()

    tree_sha = tree_data.get(
        "sha"
    )

    if not isinstance(tree_sha, str):
        fail(
            "GitHub returned an invalid tree."
        )

    new_commit_data = github_request(
        "POST",
        f"/repos/{REPOSITORY}/git/commits",
        expected_statuses=(201,),
        json={
            "message": commit_message,
            "tree": tree_sha,
            "parents": [
                base_sha,
            ],
        },
    ).json()

    new_commit_sha = new_commit_data.get(
        "sha"
    )

    if not isinstance(new_commit_sha, str):
        fail(
            "GitHub returned an invalid new commit."
        )

    existing_branch_sha = get_branch_sha(
        branch
    )

    encoded_branch = quote(
        branch,
        safe="",
    )

    if existing_branch_sha:
        github_request(
            "PATCH",
            (
                f"/repos/{REPOSITORY}/git/refs/"
                f"heads/{encoded_branch}"
            ),
            json={
                "sha": new_commit_sha,
                "force": True,
            },
        )

        print(
            "Regenerated existing automated branch "
            f"from {base_branch}: {branch}"
        )

    else:
        github_request(
            "POST",
            f"/repos/{REPOSITORY}/git/refs",
            expected_statuses=(201,),
            json={
                "ref": f"refs/heads/{branch}",
                "sha": new_commit_sha,
            },
        )

        print(
            f"Created branch: {branch}"
        )

    print(
        f"Committed opportunity file: {path}"
    )


# ============================================================
# PULL REQUEST HELPERS
# ============================================================

def get_existing_pull_request(
    owner: str,
    branch: str,
) -> dict[str, Any] | None:
    pulls = github_request(
        "GET",
        f"/repos/{REPOSITORY}/pulls",
        params={
            "state": "open",
            "head": f"{owner}:{branch}",
            "per_page": 10,
        },
    ).json()

    if not isinstance(pulls, list):
        fail(
            "GitHub returned an invalid "
            "pull-request list."
        )

    for pull in pulls:
        if isinstance(pull, dict):
            return pull

    return None


def build_pull_request_body(
    report: str,
    issue_url: str,
    opportunity_path: str,
    metadata: dict[str, str],
) -> str:
    header = [
        PR_BODY_MARKER,
        "## 🧭 OFFMAP opportunity draft",
        "",
        (
            "This opportunity was prepared from issue "
            f"#{ISSUE_NUMBER}, using the submitted "
            "information and official-source research."
        ),
        "",
        (
            "**Human review is required before merging.** "
            "Moderators may edit, request changes, reject, "
            "or approve the draft."
        ),
        "",
        f"**Proposed page:** `{opportunity_path}`",
        (
            "**Classification:** "
            f"`{metadata['main_category']}` → "
            f"`{metadata['category']}`"
        ),
        f"**Original submission:** {issue_url}",
        "",
        "---",
        "",
    ]

    body = (
        "\n".join(header)
        + report
    )

    if len(body) > MAX_PR_BODY_LENGTH:
        warn(
            "The review report exceeded the "
            "pull-request body limit and was truncated."
        )

        body = (
            body[
                : MAX_PR_BODY_LENGTH - 220
            ]
            + "\n\n---\n\n"
            + "The report was truncated. Review the "
            + f"workflow artifact `{REVIEW_REPORT_FILE.name}` "
            + "for the complete copy.\n"
        )

    return body


def create_pull_request(
    title: str,
    body: str,
    branch: str,
    base_branch: str,
) -> dict[str, Any]:
    data = github_request(
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
    ).json()

    if not isinstance(data, dict):
        fail(
            "GitHub returned an invalid "
            "pull-request object."
        )

    return data


def update_pull_request(
    pull_number: int,
    title: str,
    body: str,
) -> dict[str, Any]:
    data = github_request(
        "PATCH",
        (
            f"/repos/{REPOSITORY}/pulls/"
            f"{pull_number}"
        ),
        json={
            "title": title,
            "body": body,
        },
    ).json()

    if not isinstance(data, dict):
        fail(
            "GitHub returned an invalid updated "
            "pull request."
        )

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
        (
            f"{GITHUB_API}/repos/{REPOSITORY}/"
            f"labels/{encoded_name}"
        ),
        headers=HEADERS,
        timeout=60,
    )

    if response.status_code == 200:
        return

    if response.status_code != 404:
        fail(
            f"Could not inspect label '{name}': "
            f"{response.status_code} "
            f"{response.text[:800]}"
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
        (
            f"/repos/{REPOSITORY}/issues/"
            f"{pull_number}/labels"
        ),
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

    if response.status_code in {
        403,
        404,
        422,
    }:
        warn(
            "GitHub could not request one or more "
            "reviewers. The PR was still created or "
            "updated successfully. Confirm that the "
            "usernames are repository collaborators."
        )

        return

    fail(
        "Could not request reviewers: "
        f"{response.status_code} "
        f"{response.text[:1000]}"
    )


# ============================================================
# ORIGINAL ISSUE UPDATE
# ============================================================

def get_issue_url() -> str:
    canonical_url = (
        f"https://github.com/{REPOSITORY}/"
        f"issues/{ISSUE_NUMBER}"
    )

    if not RAW_SUBMISSION_FILE.exists():
        return canonical_url

    data = read_json(
        RAW_SUBMISSION_FILE
    )

    issue = data.get(
        "issue",
        {},
    )

    if not isinstance(issue, dict):
        return canonical_url

    value = issue.get(
        "url"
    )

    if (
        isinstance(value, str)
        and value == canonical_url
    ):
        return value

    return canonical_url


def find_existing_issue_comment() -> int | None:
    page = 1

    while True:
        comments = github_request(
            "GET",
            (
                f"/repos/{REPOSITORY}/issues/"
                f"{ISSUE_NUMBER}/comments"
            ),
            params={
                "per_page": 100,
                "page": page,
            },
        ).json()

        if not isinstance(comments, list):
            fail(
                "GitHub returned an invalid "
                "issue-comment list."
            )

        for comment in comments:
            if not isinstance(comment, dict):
                continue

            body = str(
                comment.get(
                    "body",
                    "",
                )
            )

            if (
                PR_COMMENT_MARKER in body
                or LEGACY_PR_COMMENT_MARKER in body
            ):
                comment_id = comment.get(
                    "id"
                )

                if isinstance(comment_id, int):
                    return comment_id

        if len(comments) < 100:
            return None

        page += 1


def upsert_issue_comment(
    pull_url: str,
) -> None:
    body = "\n".join(
        [
            PR_COMMENT_MARKER,
            "## ✨ An OFFMAP draft is ready",
            "",
            (
                "The opportunity has been researched "
                "and placed in a draft pull request "
                "for human review."
            ),
            "",
            f"🔗 {pull_url}",
            "",
            (
                "A moderator may edit it, request "
                "changes, reject it, or approve it "
                "for publication."
            ),
        ]
    )

    comment_id = find_existing_issue_comment()

    if comment_id is not None:
        github_request(
            "PATCH",
            (
                f"/repos/{REPOSITORY}/issues/"
                f"comments/{comment_id}"
            ),
            json={
                "body": body,
            },
        )

        print(
            "Updated the existing pull-request "
            "comment on the submission issue."
        )

        return

    github_request(
        "POST",
        (
            f"/repos/{REPOSITORY}/issues/"
            f"{ISSUE_NUMBER}/comments"
        ),
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
        (
            f"/repos/{REPOSITORY}/issues/"
            f"{ISSUE_NUMBER}/labels"
        ),
        json={
            "labels": labels,
        },
    )


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    validate_environment()

    metadata = get_publishable_metadata()

    opportunity_path = repository_path(
        OPPORTUNITY_FILE,
        metadata,
    )

    opportunity_content = read_text_file(
        OPPORTUNITY_FILE
    )

    review_report = read_text_file(
        REVIEW_REPORT_FILE
    )

    validate_opportunity_file(
        opportunity_content,
        opportunity_path,
        metadata,
    )

    repository = get_repository()

    owner = (
        repository.get(
            "owner",
            {},
        ).get(
            "login"
        )
    )

    if not isinstance(owner, str) or not owner:
        fail(
            "Could not determine the repository owner."
        )

    base_branch = get_default_branch(
        repository
    )

    # One stable branch per submission prevents duplicate PRs
    # if the generated title, slug, or category changes.
    branch = (
        f"{BRANCH_PREFIX}/issue-{ISSUE_NUMBER}"
    )[:240].rstrip("-/")

    existing_pull = get_existing_pull_request(
        owner,
        branch,
    )

    # The branch is rebuilt from the latest base tree with
    # exactly one changed opportunity file. This matches the
    # publishing workflow's one-file safety rule.
    create_single_file_branch_commit(
        branch,
        base_branch,
        opportunity_path,
        opportunity_content,
        (
            f"Add {metadata['title']} opportunity draft "
            f"(issue #{ISSUE_NUMBER})"
        ),
    )

    issue_url = get_issue_url()

    pr_body = build_pull_request_body(
        review_report,
        issue_url,
        opportunity_path,
        metadata,
    )

    pr_title = (
        "🧭 Opportunity review: "
        f"{metadata['title']}"
    )[:250]

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
            "Updated existing draft PR "
            f"#{pull_number}."
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
        pull.get("html_url")
        or ""
    )

    if not pull_url:
        fail(
            "GitHub returned no pull-request URL."
        )

    ensure_label(
        "generated-discovery",
        "8B5CF6",
        (
            "An OFFMAP opportunity draft generated "
            "from a community submission."
        ),
    )

    ensure_label(
        "needs-maintainer-review",
        "F4C542",
        (
            "Requires human review before publication."
        ),
    )

    add_labels_to_pull_request(
        pull_number,
        [
            "generated-discovery",
            "needs-maintainer-review",
        ],
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
        (
            "A draft pull request has been created "
            "for this submission."
        ),
    )

    add_labels_to_issue(
        [
            "pull-request-created",
        ]
    )

    upsert_issue_comment(
        pull_url
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
        metadata["formatter_action"],
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
