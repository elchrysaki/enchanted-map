from __future__ import annotations

import base64
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

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

RISK_OUTCOME = os.environ.get("RISK_OUTCOME", "").strip()
RISK_REASON_CODE = os.environ.get("RISK_REASON_CODE", "").strip()

INTAKE_OUTCOME = os.environ.get("INTAKE_OUTCOME", "").strip()
RESEARCH_OUTCOME = os.environ.get("RESEARCH_OUTCOME", "").strip()
RECONCILE_OUTCOME = os.environ.get("RECONCILE_OUTCOME", "").strip()
FORMATTER_OUTCOME = os.environ.get("FORMATTER_OUTCOME", "").strip()
GENERATOR_OUTCOME = os.environ.get("GENERATOR_OUTCOME", "").strip()
REVIEW_OUTCOME = os.environ.get("REVIEW_OUTCOME", "").strip()

SAFE_TO_RESEARCH = os.environ.get("SAFE_TO_RESEARCH", "").strip()
SAFE_TO_GENERATE = os.environ.get("SAFE_TO_GENERATE", "").strip()
RESEARCH_RECOMMENDATION = os.environ.get(
    "RESEARCH_RECOMMENDATION",
    "",
).strip()
FORMATTER_RECOMMENDATION = os.environ.get(
    "FORMATTER_RECOMMENDATION",
    "",
).strip()
MODERATORS = os.environ.get("MODERATORS", "").strip()

RAW_SUBMISSION_FILE = Path(
    os.environ.get(
        "RAW_SUBMISSION_FILE",
        "",
    )
    or f"artifacts/raw-submission-{ISSUE_NUMBER}.json"
)
RESEARCHED_SUBMISSION_FILE = Path(
    os.environ.get(
        "RESEARCHED_SUBMISSION_FILE",
        "",
    )
    or f"artifacts/researched-submission-{ISSUE_NUMBER}.json"
)
PUBLISHABLE_CONTENT_FILE = Path(
    os.environ.get(
        "PUBLISHABLE_CONTENT_FILE",
        "",
    )
    or f"artifacts/publishable-content-{ISSUE_NUMBER}.json"
)
OPPORTUNITY_FILE_VALUE = os.environ.get(
    "OPPORTUNITY_FILE",
    "",
).strip()
OPPORTUNITY_FILE = (
    Path(OPPORTUNITY_FILE_VALUE)
    if OPPORTUNITY_FILE_VALUE
    else None
)
REVIEW_REPORT_FILE = Path(
    os.environ.get(
        "REVIEW_REPORT_FILE",
        "",
    )
    or f"artifacts/review-report-{ISSUE_NUMBER}.md"
)

BRANCH_PREFIX = os.environ.get(
    "BRANCH_PREFIX",
    "automated-discovery",
).strip("/")

MAX_TEXT = 60_000
MAX_FILE_BYTES = 2_000_000

PROCESS_COMMENT_MARKER = "<!-- offmap-processing-complete -->"
SECURITY_COMMENT_MARKER = "<!-- offmap-security-rejected -->"
FAILURE_COMMENT_MARKER = "<!-- offmap-finalization-failed -->"
PR_BODY_MARKER = "<!-- offmap-terminal-outcome-pr -->"
REVIEW_PACKET_MARKER = "<!-- offmap-review-packet -->"

LABELS = {
    "processed": (
        "0E8A16",
        "Submission processing reached a terminal review result.",
    ),
    "draft-created": (
        "6F42C1",
        "A draft pull request was created for moderator review.",
    ),
    "needs-human-research": (
        "FBCA04",
        "A moderator must research or complete missing information.",
    ),
    "automation-recovery": (
        "D93F0B",
        "Automation failed but a recovery review pull request exists.",
    ),
    "technical-review": (
        "D4C5F9",
        "A technical mismatch needs human correction.",
    ),
    "security-rejected": (
        "B60205",
        "Submission triggered severe technical abuse protections.",
    ),
    "workflow-failed": (
        "B60205",
        "The workflow could not create its required terminal result.",
    ),
}


class FinalizationError(RuntimeError):
    pass


def neutralize_mentions(value: str) -> str:
    return value.replace("@", "@\u200b")


def truncate(value: str, maximum: int = MAX_TEXT) -> str:
    value = value.strip()
    if len(value) <= maximum:
        return value
    return value[: maximum - 1].rstrip() + "…"


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
        detail = response.text[:1500]
        raise FinalizationError(
            f"GitHub API request failed: {method} {endpoint} "
            f"returned {response.status_code}. {detail}"
        )
    return response


def write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        print(f"{name}={value}")
        return
    with open(output_path, "a", encoding="utf-8") as output:
        output.write(f"{name}={value}\n")


def get_issue() -> dict[str, Any]:
    issue = github_request(
        "GET",
        f"/repos/{REPOSITORY}/issues/{ISSUE_NUMBER}",
    ).json()
    if not isinstance(issue, dict) or issue.get("pull_request"):
        raise FinalizationError("The workflow issue could not be read.")
    return issue


def get_repository() -> dict[str, Any]:
    repository = github_request(
        "GET",
        f"/repos/{REPOSITORY}",
    ).json()
    if not isinstance(repository, dict):
        raise FinalizationError("Repository metadata was invalid.")
    return repository


def ensure_label(name: str) -> None:
    color, description = LABELS[name]
    response = requests.post(
        f"{GITHUB_API}/repos/{REPOSITORY}/labels",
        headers=HEADERS,
        timeout=45,
        json={
            "name": name,
            "color": color,
            "description": description,
        },
    )
    if response.status_code not in {201, 422}:
        raise FinalizationError(
            f"Could not create or verify label '{name}'."
        )


def add_labels(names: list[str]) -> None:
    unique_names = list(dict.fromkeys(names))
    for name in unique_names:
        ensure_label(name)

    github_request(
        "POST",
        f"/repos/{REPOSITORY}/issues/{ISSUE_NUMBER}/labels",
        expected_statuses=(200,),
        json={"labels": unique_names},
    )


def remove_label(name: str) -> None:
    encoded = quote(name, safe="")
    response = requests.delete(
        (
            f"{GITHUB_API}/repos/{REPOSITORY}/issues/"
            f"{ISSUE_NUMBER}/labels/{encoded}"
        ),
        headers=HEADERS,
        timeout=45,
    )
    if response.status_code not in {200, 404}:
        raise FinalizationError(
            f"Could not remove issue label '{name}'."
        )


def close_issue(*, state_reason: str) -> None:
    github_request(
        "PATCH",
        f"/repos/{REPOSITORY}/issues/{ISSUE_NUMBER}",
        json={
            "state": "closed",
            "state_reason": state_reason,
        },
    )


def keep_issue_open() -> None:
    github_request(
        "PATCH",
        f"/repos/{REPOSITORY}/issues/{ISSUE_NUMBER}",
        json={"state": "open"},
    )


def lock_issue() -> None:
    github_request(
        "PUT",
        f"/repos/{REPOSITORY}/issues/{ISSUE_NUMBER}/lock",
        expected_statuses=(204,),
        json={"lock_reason": "spam"},
    )


def issue_comments() -> list[dict[str, Any]]:
    response = github_request(
        "GET",
        f"/repos/{REPOSITORY}/issues/{ISSUE_NUMBER}/comments",
        params={"per_page": 100},
    )
    data = response.json()
    return data if isinstance(data, list) else []


def upsert_issue_comment(marker: str, body: str) -> None:
    body = truncate(body)
    for comment in issue_comments():
        if not isinstance(comment, dict):
            continue
        existing_body = str(comment.get("body") or "")
        if marker not in existing_body:
            continue
        comment_id = comment.get("id")
        if not isinstance(comment_id, int):
            continue
        github_request(
            "PATCH",
            f"/repos/{REPOSITORY}/issues/comments/{comment_id}",
            json={"body": body},
        )
        return

    github_request(
        "POST",
        f"/repos/{REPOSITORY}/issues/{ISSUE_NUMBER}/comments",
        expected_statuses=(201,),
        json={"body": body},
    )


def safe_read_text(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    if path.stat().st_size > MAX_FILE_BYTES:
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def repo_relative_path(path: Path) -> str:
    resolved = path.resolve()
    root = Path.cwd().resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise FinalizationError(
            f"Generated file is outside the repository: {path}"
        ) from exc


def stage_rows() -> list[tuple[str, str, str]]:
    return [
        (
            "Severe-risk preflight",
            RISK_OUTCOME or "not reported",
            RISK_REASON_CODE or "none",
        ),
        (
            "Intake",
            INTAKE_OUTCOME or "not run",
            f"safe_to_research={SAFE_TO_RESEARCH or 'not set'}",
        ),
        (
            "Official research",
            RESEARCH_OUTCOME or "not run",
            RESEARCH_RECOMMENDATION or "no recommendation",
        ),
        (
            "Category reconciliation",
            RECONCILE_OUTCOME or "not run",
            "keeps main and specific categories paired",
        ),
        (
            "Formatting",
            FORMATTER_OUTCOME or "not run",
            FORMATTER_RECOMMENDATION or "no recommendation",
        ),
        (
            "Opportunity generation",
            GENERATOR_OUTCOME or "not run",
            (
                f"safe_to_generate={SAFE_TO_GENERATE or 'not set'}"
            ),
        ),
        (
            "Moderator report",
            REVIEW_OUTCOME or "not run",
            "report is included when available",
        ),
    ]


def determine_outcome() -> tuple[str, str, list[str]]:
    opportunity_exists = (
        OPPORTUNITY_FILE is not None
        and OPPORTUNITY_FILE.exists()
        and OPPORTUNITY_FILE.is_file()
    )

    if RISK_OUTCOME == "security-rejected":
        return (
            "security-rejected",
            "Severe technical abuse or automated spam was detected.",
            [],
        )

    if opportunity_exists:
        return (
            "ready-for-review",
            (
                "A reviewable opportunity page was generated. "
                "Human approval is still required."
            ),
            [
                "Verify the official evidence and corrected values.",
                "Confirm the category pair, deadline, funding, and eligibility.",
                "Approve, edit, or close the draft pull request.",
            ],
        )

    if INTAKE_OUTCOME != "success":
        return (
            "automation-recovery-required",
            (
                "The intake stage did not complete, so OffMap created "
                "a recovery pull request instead of losing the submission."
            ),
            [
                "Read the original issue.",
                "Repair or complete the intake record.",
                "Rerun the workflow or prepare the opportunity manually.",
            ],
        )

    if SAFE_TO_RESEARCH != "true":
        return (
            "human-research-required",
            (
                "The submission was preserved, but automated research "
                "could not safely use the supplied source."
            ),
            [
                "Check or replace the official source URL.",
                "Research the opportunity manually.",
                "Create the opportunity page only after verification.",
            ],
        )

    if RESEARCH_OUTCOME != "success":
        return (
            "automation-recovery-required",
            (
                "Official-source research failed or returned unusable data. "
                "The original submission remains available for a moderator."
            ),
            [
                "Review the source website manually.",
                "Check the workflow artifact and research error.",
                "Rerun research or complete the record manually.",
            ],
        )

    if RECONCILE_OUTCOME != "success":
        return (
            "technical-review-required",
            (
                "The researched classification could not be normalized "
                "into a valid main-category and specific-category pair."
            ),
            [
                "Confirm the official opportunity type.",
                "Correct both category fields as one valid pair.",
                "Continue formatting after the category is resolved.",
            ],
        )

    if FORMATTER_OUTCOME != "success":
        return (
            "automation-recovery-required",
            (
                "The researched record could not be converted into "
                "publishable structured content."
            ),
            [
                "Inspect the researched JSON and formatting error.",
                "Correct missing or incompatible fields.",
                "Rerun formatting or prepare the page manually.",
            ],
        )

    if (
        SAFE_TO_GENERATE != "true"
        or FORMATTER_RECOMMENDATION != "continue-to-draft-pr"
    ):
        return (
            "human-research-required",
            (
                "Research completed, but the formatter found information "
                "that needs human judgment before a page can be generated."
            ),
            [
                "Review missing, unclear, or conflicting fields.",
                "Verify claims against current official evidence.",
                "Complete the opportunity page after resolving the warnings.",
            ],
        )

    if GENERATOR_OUTCOME != "success":
        return (
            "technical-review-required",
            (
                "The publishable data exists, but page generation found "
                "a technical or schema mismatch."
            ),
            [
                "Read the generator error.",
                "Correct mirrored filters and schema fields.",
                "Regenerate the opportunity page.",
            ],
        )

    return (
        "human-research-required",
        (
            "The workflow reached no publishable page, but the submission "
            "can still be resolved by a moderator."
        ),
        [
            "Review every available artifact.",
            "Complete the missing research.",
            "Create or regenerate the opportunity page.",
        ],
    )


def outcome_label(outcome: str) -> str:
    return {
        "ready-for-review": "draft-created",
        "human-research-required": "needs-human-research",
        "automation-recovery-required": "automation-recovery",
        "technical-review-required": "technical-review",
    }.get(outcome, "needs-human-research")


def artifact_list() -> list[str]:
    candidates = [
        RAW_SUBMISSION_FILE,
        RESEARCHED_SUBMISSION_FILE,
        PUBLISHABLE_CONTENT_FILE,
        REVIEW_REPORT_FILE,
    ]
    if OPPORTUNITY_FILE is not None:
        candidates.append(OPPORTUNITY_FILE)

    return [
        path.as_posix()
        for path in candidates
        if path.exists() and path.is_file()
    ]


def processing_log_section() -> str:
    log_paths = [
        Path("artifacts/risk.log"),
        Path("artifacts/intake.log"),
        Path("artifacts/research.log"),
        Path("artifacts/reconcile.log"),
        Path("artifacts/formatter.log"),
        Path("artifacts/generator.log"),
        Path("artifacts/review.log"),
    ]
    sections: list[str] = []

    for path in log_paths:
        content = safe_read_text(path)
        if not content:
            continue
        tail = content[-4_000:]
        sections.append(
            f"### `{path.name}`\n\n"
            f"```text\n{neutralize_mentions(tail)}\n```"
        )

    if not sections:
        return ""

    return (
        "\n\n## Processing log excerpts\n\n"
        + "\n\n".join(sections)
    )


def markdown_stage_table() -> str:
    lines = [
        "| Stage | Result | Detail |",
        "|---|---|---|",
    ]
    for stage, result, detail in stage_rows():
        safe_stage = neutralize_mentions(stage).replace("|", "\\|")
        safe_result = neutralize_mentions(result).replace("|", "\\|")
        safe_detail = neutralize_mentions(detail).replace("|", "\\|")
        lines.append(
            f"| {safe_stage} | `{safe_result}` | {safe_detail} |"
        )
    return "\n".join(lines)


def build_review_packet(
    issue: dict[str, Any],
    *,
    outcome: str,
    explanation: str,
    human_tasks: list[str],
) -> str:
    issue_title = neutralize_mentions(
        str(issue.get("title") or "Untitled submission")
    )
    issue_url = str(issue.get("html_url") or "")
    author = issue.get("user")
    author_login = (
        neutralize_mentions(str(author.get("login") or "unknown"))
        if isinstance(author, dict)
        else "unknown"
    )
    now = datetime.now(timezone.utc).isoformat()

    task_lines = "\n".join(
        f"{index}. {neutralize_mentions(task)}"
        for index, task in enumerate(human_tasks, start=1)
    )
    files = artifact_list()
    file_lines = (
        "\n".join(f"- `{neutralize_mentions(path)}`" for path in files)
        if files
        else "- No processing artifact was successfully created."
    )

    existing_report = safe_read_text(REVIEW_REPORT_FILE)
    existing_section = ""
    if existing_report:
        existing_section = (
            "\n\n## Existing automated moderator report\n\n"
            + neutralize_mentions(
                truncate(existing_report, 25_000)
            )
        )

    log_section = (
        ""
        if outcome == "ready-for-review"
        else processing_log_section()
    )

    return truncate(
        f"""{REVIEW_PACKET_MARKER}
# OffMap moderator review for issue #{ISSUE_NUMBER}

> [!WARNING]
> This file is a review packet, not a published opportunity. A human must
> verify the evidence and decide what happens next.

## Processing outcome

**Outcome:** `{outcome}`

{neutralize_mentions(explanation)}

## Original submission

- **Issue:** [{issue_title}]({issue_url})
- **Submitted by:** `{author_login}`
- **Processed at:** `{now}`
- **Original issue preserved:** Yes

## Workflow stages

{markdown_stage_table()}

## Human tasks

{task_lines or "1. Review the original submission and available evidence."}

## Available processing records

{file_lines}

## Important rules

- Official current evidence takes precedence over contributor claims.
- Contributor values remain preserved in the original issue and raw record.
- Conflicts should be corrected in the draft and explained, not hidden.
- `audience.groups` remains controlled only by the submitted dropdown.
- Nothing is published until a human approves and merges a valid page.
{existing_section}
{log_section}
"""
    )


def get_base_branch_and_sha() -> tuple[str, str]:
    repository = get_repository()
    base_branch = str(
        repository.get("default_branch") or "main"
    ).strip()
    encoded = quote(f"heads/{base_branch}", safe="/")
    reference = github_request(
        "GET",
        f"/repos/{REPOSITORY}/git/ref/{encoded}",
    ).json()
    try:
        sha = reference["object"]["sha"]
    except (KeyError, TypeError) as exc:
        raise FinalizationError(
            "Could not determine the base branch commit."
        ) from exc
    return base_branch, str(sha)


def branch_ref(branch: str) -> dict[str, Any] | None:
    encoded = quote(f"heads/{branch}", safe="/")
    response = requests.get(
        f"{GITHUB_API}/repos/{REPOSITORY}/git/ref/{encoded}",
        headers=HEADERS,
        timeout=45,
    )
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise FinalizationError(
            f"Could not read branch '{branch}'."
        )
    data = response.json()
    return data if isinstance(data, dict) else None


def ensure_branch(branch: str, base_sha: str) -> None:
    if branch_ref(branch) is not None:
        return
    github_request(
        "POST",
        f"/repos/{REPOSITORY}/git/refs",
        expected_statuses=(201,),
        json={
            "ref": f"refs/heads/{branch}",
            "sha": base_sha,
        },
    )


def content_sha(path: str, branch: str) -> str | None:
    encoded_path = quote(path, safe="/")
    response = requests.get(
        f"{GITHUB_API}/repos/{REPOSITORY}/contents/{encoded_path}",
        headers=HEADERS,
        timeout=45,
        params={"ref": branch},
    )
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise FinalizationError(
            f"Could not inspect '{path}' on branch '{branch}'."
        )
    data = response.json()
    if not isinstance(data, dict):
        return None
    sha = data.get("sha")
    return str(sha) if sha else None


def upsert_branch_file(
    *,
    branch: str,
    path: str,
    content: str,
    message: str,
) -> None:
    payload: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(
            content.encode("utf-8")
        ).decode("ascii"),
        "branch": branch,
    }
    existing_sha = content_sha(path, branch)
    if existing_sha:
        payload["sha"] = existing_sha

    encoded_path = quote(path, safe="/")
    github_request(
        "PUT",
        f"/repos/{REPOSITORY}/contents/{encoded_path}",
        expected_statuses=(200, 201),
        json=payload,
    )


def find_pull_request(branch: str) -> dict[str, Any] | None:
    owner = REPOSITORY.split("/", 1)[0]
    response = github_request(
        "GET",
        f"/repos/{REPOSITORY}/pulls",
        params={
            "state": "open",
            "head": f"{owner}:{branch}",
            "per_page": 10,
        },
    )
    data = response.json()
    if isinstance(data, list) and data:
        first = data[0]
        return first if isinstance(first, dict) else None
    return None


def create_or_update_pull_request(
    *,
    branch: str,
    base_branch: str,
    title: str,
    body: str,
) -> dict[str, Any]:
    existing = find_pull_request(branch)
    if existing:
        number = existing.get("number")
        if not isinstance(number, int):
            raise FinalizationError(
                "Existing pull request had no valid number."
            )
        updated = github_request(
            "PATCH",
            f"/repos/{REPOSITORY}/pulls/{number}",
            json={
                "title": title,
                "body": truncate(body),
                "base": base_branch,
            },
        ).json()
        if not isinstance(updated, dict):
            raise FinalizationError(
                "Updated pull request response was invalid."
            )
        return updated

    created = github_request(
        "POST",
        f"/repos/{REPOSITORY}/pulls",
        expected_statuses=(201,),
        json={
            "title": title,
            "body": truncate(body),
            "head": branch,
            "base": base_branch,
            "draft": True,
            "maintainer_can_modify": True,
        },
    ).json()
    if not isinstance(created, dict):
        raise FinalizationError(
            "Created pull request response was invalid."
        )
    return created


def reviewer_names() -> list[str]:
    values: list[str]

    try:
        parsed = json.loads(MODERATORS)
    except (json.JSONDecodeError, TypeError):
        parsed = None

    if isinstance(parsed, list):
        values = [str(item) for item in parsed]
    else:
        values = re.split(r"[\s,]+", MODERATORS)

    reviewers: list[str] = []
    for value in values:
        value = value.strip()
        if not re.fullmatch(
            r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})",
            value,
        ):
            continue
        if value not in reviewers:
            reviewers.append(value)

    return reviewers[:15]


def request_reviewers(pr_number: int) -> None:
    reviewers = reviewer_names()
    if not reviewers:
        return
    response = requests.post(
        (
            f"{GITHUB_API}/repos/{REPOSITORY}/pulls/"
            f"{pr_number}/requested_reviewers"
        ),
        headers=HEADERS,
        timeout=45,
        json={"reviewers": reviewers},
    )
    if response.status_code not in {201, 422}:
        print(
            "::warning::Could not request all configured reviewers."
        )


def build_pr_body(
    *,
    outcome: str,
    explanation: str,
    issue_url: str,
    review_packet_path: str,
    opportunity_path: str | None,
) -> str:
    file_lines = [f"- `{review_packet_path}`"]
    if opportunity_path:
        file_lines.insert(0, f"- `{opportunity_path}`")

    return f"""{PR_BODY_MARKER}
## OffMap processing result

**Outcome:** `{outcome}`

{neutralize_mentions(explanation)}

Processed from [issue #{ISSUE_NUMBER}]({issue_url}). The issue is closed only
after this draft pull request is created successfully.

### Files in this review

{chr(10).join(file_lines)}

### Moderator decision

- Verify the official evidence.
- Correct anything uncertain or conflicting.
- Keep the opportunity page at `pending-review` until approved.
- Remove `review-packets/issue-{ISSUE_NUMBER}.md` before merging.
- Merge only when the page is publishable.
- Close this pull request without merging if the opportunity is unsuitable.
"""


def finalize_with_pull_request(
    issue: dict[str, Any],
    *,
    outcome: str,
    explanation: str,
    human_tasks: list[str],
) -> tuple[str, int]:
    base_branch, base_sha = get_base_branch_and_sha()
    branch = f"{BRANCH_PREFIX}/issue-{ISSUE_NUMBER}"
    ensure_branch(branch, base_sha)

    packet = build_review_packet(
        issue,
        outcome=outcome,
        explanation=explanation,
        human_tasks=human_tasks,
    )
    review_packet_path = (
        f"review-packets/issue-{ISSUE_NUMBER}.md"
    )
    upsert_branch_file(
        branch=branch,
        path=review_packet_path,
        content=packet,
        message=(
            f"Add moderator review packet for issue #{ISSUE_NUMBER}"
        ),
    )

    opportunity_path: str | None = None
    if (
        OPPORTUNITY_FILE is not None
        and OPPORTUNITY_FILE.exists()
        and OPPORTUNITY_FILE.is_file()
    ):
        opportunity_path = repo_relative_path(OPPORTUNITY_FILE)
        opportunity_content = safe_read_text(OPPORTUNITY_FILE)
        if opportunity_content is None:
            raise FinalizationError(
                "Generated opportunity file could not be read."
            )
        upsert_branch_file(
            branch=branch,
            path=opportunity_path,
            content=opportunity_content,
            message=(
                f"Add opportunity draft for issue #{ISSUE_NUMBER}"
            ),
        )

    issue_title = neutralize_mentions(
        str(issue.get("title") or f"Issue #{ISSUE_NUMBER}")
    )
    title_prefix = (
        "Opportunity review"
        if outcome == "ready-for-review"
        else "Human review"
    )
    title = truncate(
        f"[{title_prefix} #{ISSUE_NUMBER}] {issue_title}",
        240,
    )
    issue_url = str(issue.get("html_url") or "")
    pr_body = build_pr_body(
        outcome=outcome,
        explanation=explanation,
        issue_url=issue_url,
        review_packet_path=review_packet_path,
        opportunity_path=opportunity_path,
    )
    pr = create_or_update_pull_request(
        branch=branch,
        base_branch=base_branch,
        title=title,
        body=pr_body,
    )

    pr_number = pr.get("number")
    pr_url = str(pr.get("html_url") or "")
    if not isinstance(pr_number, int) or not pr_url:
        raise FinalizationError(
            "Pull request was created without a valid URL."
        )

    request_reviewers(pr_number)

    add_labels(
        [
            "processed",
            "draft-created",
            outcome_label(outcome),
        ]
    )
    for label in ("new-discovery", "processing"):
        remove_label(label)

    comment = f"""{PROCESS_COMMENT_MARKER}
## OffMap processing complete

This discovery has been transferred to draft pull request
[#{pr_number}]({pr_url}).

**Result:** `{outcome}`

The original submission remains preserved in this issue. Research,
corrections, missing information, and moderator decisions now continue in the
pull request.
"""
    upsert_issue_comment(
        PROCESS_COMMENT_MARKER,
        comment,
    )
    close_issue(state_reason="completed")

    return pr_url, pr_number


def finalize_security_rejection() -> None:
    add_labels(["security-rejected"])
    for label in ("new-discovery", "processing"):
        remove_label(label)

    comment = f"""{SECURITY_COMMENT_MARKER}
## Submission closed

This submission triggered OffMap's severe technical abuse or automated-spam
protections. It was not sent to website research and no pull request was
created.

For security reasons, detailed detection rules are not published.
"""
    upsert_issue_comment(
        SECURITY_COMMENT_MARKER,
        comment,
    )
    close_issue(state_reason="not_planned")
    lock_issue()


def record_finalization_failure(message: str) -> None:
    try:
        add_labels(["workflow-failed"])
        keep_issue_open()
        safe_message = neutralize_mentions(
            truncate(message, 1200)
        )
        comment = f"""{FAILURE_COMMENT_MARKER}
## OffMap processing needs attention

The workflow could not create the required pull request or security-rejection
result, so this issue has been kept open.

**Finalization error:** `{safe_message}`

A maintainer should inspect the workflow run and retry after correcting the
problem.
"""
        upsert_issue_comment(
            FAILURE_COMMENT_MARKER,
            comment,
        )
    except Exception as secondary_error:
        print(
            "::error::Could not record finalization failure: "
            f"{secondary_error}"
        )


def main() -> None:
    issue = get_issue()
    outcome, explanation, human_tasks = determine_outcome()

    if outcome == "security-rejected":
        finalize_security_rejection()
        write_output("terminal_outcome", outcome)
        write_output("pull_request_url", "")
        print(
            "Severe-risk submission closed and locked. "
            "No pull request was created."
        )
        return

    pr_url, pr_number = finalize_with_pull_request(
        issue,
        outcome=outcome,
        explanation=explanation,
        human_tasks=human_tasks,
    )
    write_output("terminal_outcome", outcome)
    write_output("pull_request_url", pr_url)
    write_output("pull_request_number", str(pr_number))
    print(
        f"Terminal outcome '{outcome}' created draft PR #{pr_number}."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        record_finalization_failure(str(exc))
        raise
