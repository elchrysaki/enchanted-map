from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


# ============================================================
# ENVIRONMENT
# ============================================================

ISSUE_NUMBER = int(os.environ["ISSUE_NUMBER"])

RESEARCHED_SUBMISSION_FILE = Path(
    os.environ.get(
        "RESEARCHED_SUBMISSION_FILE",
        f"artifacts/researched-submission-{ISSUE_NUMBER}.json",
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

OPPORTUNITY_FILE_VALUE = os.environ.get(
    "OPPORTUNITY_FILE",
    "",
).strip()

OPPORTUNITY_FILE: Path | None = (
    Path(OPPORTUNITY_FILE_VALUE)
    if OPPORTUNITY_FILE_VALUE
    else None
)

REVIEW_REPORT_FILE = Path(
    os.environ.get(
        "REVIEW_REPORT_FILE",
        f"artifacts/review-report-{ISSUE_NUMBER}.md",
    )
)

MAX_ITEMS_PER_SECTION = 100
MAX_TEXT_LENGTH = 10_000
ALLOWED_SCHEMES = {"http", "https"}


# ============================================================
# BASIC HELPERS
# ============================================================

def fail(message: str) -> None:
    print(f"::error::{message}")
    raise SystemExit(1)


def warn(message: str) -> None:
    print(f"::warning::{message}")


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


def write_github_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")

    if not output_path:
        print(f"{name}={value}")
        return

    with open(output_path, "a", encoding="utf-8") as output:
        output.write(f"{name}={value}\n")


def clean_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH].rstrip() + "â¦"

    return text


def safe_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    candidate = value.strip()

    if not candidate or len(candidate) > 2_000:
        return None

    try:
        parsed = urlparse(candidate)
    except ValueError:
        return None

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        return None

    if not parsed.hostname:
        return None

    if parsed.username or parsed.password:
        return None

    return candidate


def neutralize_mentions(value: str) -> str:
    return value.replace("@", "@\u200b")


def markdown_escape(value: str) -> str:
    return (
        neutralize_mentions(value)
        .replace("\\", "\\\\")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def markdown_link(label: str, url: str) -> str:
    return f"[{markdown_escape(label)}]({url})"


def unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        cleaned = clean_text(value)

        if not cleaned:
            continue

        key = cleaned.casefold()

        if key in seen:
            continue

        seen.add(key)
        result.append(cleaned)

        if len(result) >= MAX_ITEMS_PER_SECTION:
            break

    return result


def get_object(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)

    if isinstance(value, dict):
        return value

    return {}


def get_list(parent: dict[str, Any], key: str) -> list[Any]:
    value = parent.get(key)

    if isinstance(value, list):
        return value

    return []


# ============================================================
# RESEARCH SUMMARY EXTRACTION
# ============================================================

def normalize_summary_items(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    result: list[str] = []

    for item in values:
        if isinstance(item, str):
            cleaned = clean_text(item)

            if cleaned:
                result.append(cleaned)

        elif isinstance(item, dict):
            field = clean_text(item.get("field"))
            message = (
                clean_text(item.get("message"))
                or clean_text(item.get("finding"))
                or clean_text(item.get("researched_claim"))
                or clean_text(item.get("recommended_moderator_action"))
            )

            if field and message:
                result.append(f"{field}: {message}")
            elif message:
                result.append(message)
            elif field:
                result.append(field)

    return unique_strings(result)


def extract_conflicts(
    research_summary: dict[str, Any],
    publication_notes: dict[str, Any],
) -> list[str]:
    conflicts = normalize_summary_items(
        research_summary.get("possible_conflicts")
    )

    conflicts.extend(
        normalize_summary_items(
            publication_notes.get("conflicts")
        )
    )

    return unique_strings(conflicts)


def extract_missing_information(
    research_summary: dict[str, Any],
    publication_notes: dict[str, Any],
) -> list[str]:
    missing = normalize_summary_items(
        research_summary.get(
            "important_information_not_found"
        )
    )

    missing.extend(
        normalize_summary_items(
            publication_notes.get("missing_information")
        )
    )

    return unique_strings(missing)


def extract_human_review_items(
    research_summary: dict[str, Any],
    publication_notes: dict[str, Any],
) -> list[str]:
    items = normalize_summary_items(
        research_summary.get(
            "requires_human_judgment"
        )
    )

    items.extend(
        normalize_summary_items(
            publication_notes.get("human_review")
        )
    )

    items.extend(
        normalize_summary_items(
            research_summary.get("moderator_focus")
        )
    )

    return unique_strings(items)


def extract_excluded_claims(
    publication_notes: dict[str, Any],
) -> list[str]:
    return normalize_summary_items(
        publication_notes.get("excluded_claims")
    )


def extract_confirmed(
    research_summary: dict[str, Any],
) -> list[str]:
    confirmed = normalize_summary_items(
        research_summary.get("confirmed_fields")
    )

    clarified = normalize_summary_items(
        research_summary.get(
            "confirmed_with_clarification"
        )
    )

    confirmed.extend(
        f"{item} (clarified)"
        for item in clarified
    )

    return unique_strings(confirmed)


def extract_link_problems(
    research_summary: dict[str, Any],
) -> list[str]:
    return normalize_summary_items(
        research_summary.get(
            "incorrect_or_outdated_links"
        )
    )


# ============================================================
# SOURCE EXTRACTION
# ============================================================

def extract_sources(
    researched: dict[str, Any],
) -> list[dict[str, str]]:
    research_summary = get_object(
        researched,
        "research_summary",
    )

    source_items = research_summary.get(
        "sources_checked",
        [],
    )

    if not isinstance(source_items, list):
        return []

    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for item in source_items:
        if isinstance(item, str):
            url = safe_url(item)

            if not url or url in seen_urls:
                continue

            seen_urls.add(url)

            results.append(
                {
                    "label": "Source",
                    "url": url,
                }
            )

            continue

        if not isinstance(item, dict):
            continue

        url = safe_url(
            item.get("url")
            or item.get("final_url")
        )

        if not url or url in seen_urls:
            continue

        seen_urls.add(url)

        label = (
            clean_text(item.get("page_title"))
            or clean_text(item.get("source_type"))
            or clean_text(item.get("title"))
            or "Source"
        )

        results.append(
            {
                "label": label,
                "url": url,
            }
        )

        if len(results) >= MAX_ITEMS_PER_SECTION:
            break

    return results


# ============================================================
# REPORT SECTIONS
# ============================================================

def add_bullet_section(
    lines: list[str],
    heading: str,
    items: list[str],
    *,
    empty_message: str | None = None,
) -> None:
    lines.extend(
        [
            f"## {heading}",
            "",
        ]
    )

    if items:
        for item in items:
            lines.append(
                f"- {markdown_escape(item)}"
            )
    elif empty_message:
        lines.append(
            f"- {markdown_escape(empty_message)}"
        )

    lines.append("")


def add_source_section(
    lines: list[str],
    sources: list[dict[str, str]],
) -> None:
    lines.extend(
        [
            "## ð Sources Checked",
            "",
        ]
    )

    if not sources:
        lines.append(
            "- No source list was returned by the research stage."
        )
        lines.append("")
        return

    for source in sources:
        label = source["label"]
        url = source["url"]

        lines.append(
            f"- {markdown_link(label, url)}"
        )

    lines.append("")


def add_metadata_table(
    lines: list[str],
    researched: dict[str, Any],
    publishable: dict[str, Any],
) -> None:
    identity = get_object(
        publishable,
        "identity",
    )

    moderation = get_object(
        publishable,
        "moderation",
    )

    summary = get_object(
        researched,
        "research_summary",
    )

    provenance = get_object(
        researched,
        "provenance",
    )

    issue_url = safe_url(
        provenance.get("original_issue_url")
    )

    title = clean_text(
        identity.get("title")
    ) or "Untitled opportunity"

    category = clean_text(
        identity.get("category")
    ) or "other"

    action = clean_text(
        moderation.get("recommended_action")
    ) or "not provided"

    research_action = clean_text(
        summary.get("recommended_action")
    ) or "not provided"

    confidence = summary.get(
        "overall_confidence",
        0,
    )

    safe_to_generate = moderation.get(
        "safe_to_generate_draft_page",
        False,
    )

    lines.extend(
        [
            "## ð§¾ Review Snapshot",
            "",
            "| Field | Value |",
            "|---|---|",
            f"| Opportunity | {markdown_escape(title)} |",
            f"| Category | `{markdown_escape(category)}` |",
            f"| Research confidence | `{confidence}` |",
            f"| Research action | `{markdown_escape(research_action)}` |",
            f"| Formatter action | `{markdown_escape(action)}` |",
            (
                "| Draft page considered safe to generate | "
                f"`{str(bool(safe_to_generate)).lower()}` |"
            ),
        ]
    )

    if issue_url:
        lines.append(
            "| Original issue | "
            f"{markdown_link('Open submission', issue_url)} |"
        )

    if OPPORTUNITY_FILE:
        lines.append(
            "| Proposed quest page | "
            f"`{markdown_escape(str(OPPORTUNITY_FILE))}` |"
        )

    lines.append("")


def add_checklist(
    lines: list[str],
    publishable: dict[str, Any],
) -> None:
    moderation = get_object(
        publishable,
        "moderation",
    )

    safe_to_generate = bool(
        moderation.get(
            "safe_to_generate_draft_page",
            False,
        )
    )

    lines.extend(
        [
            "## ð¡ï¸ Human Review Checklist",
            "",
            "- [ ] Confirm the opportunity and organizer are correctly identified.",
            "- [ ] Open the official and application links.",
            "- [ ] Confirm the deadline and edition are current.",
            "- [ ] Review geographic and academic eligibility.",
            "- [ ] Review audience wording without broadening or changing identity groups.",
            "- [ ] Confirm fees, travel, accommodation, scholarships, and other support.",
            "- [ ] Remove or rewrite any unsupported public claim.",
            "- [ ] Confirm the YAML filters match the approved page.",
        ]
    )

    if not safe_to_generate:
        lines.append(
            "- [ ] Resolve why the formatter marked the draft unsafe before merging."
        )

    lines.extend(
        [
            "- [ ] Approve the final page for publication.",
            "",
            "> Merging remains a human decision. "
            "This report is advisory and cannot approve or publish the quest.",
            "",
        ]
    )


# ============================================================
# REPORT GENERATION
# ============================================================

def validate_inputs(
    researched: dict[str, Any],
    publishable: dict[str, Any],
) -> None:
    if (
        researched.get("record_type")
        != "researched-submission"
    ):
        fail(
            "Research input is not a researched-submission record."
        )

    if (
        publishable.get("record_type")
        != "publishable-opportunity-draft"
    ):
        fail(
            "Publishable input is not a "
            "publishable-opportunity-draft record."
        )

    moderation = get_object(
        publishable,
        "moderation",
    )

    if moderation.get("human_review_required") is not True:
        fail(
            "The publishable draft must require human review."
        )


def build_report(
    researched: dict[str, Any],
    publishable: dict[str, Any],
) -> str:
    research_summary = get_object(
        researched,
        "research_summary",
    )

    publication_notes = get_object(
        publishable,
        "publication_notes",
    )

    confirmed = extract_confirmed(
        research_summary
    )

    conflicts = extract_conflicts(
        research_summary,
        publication_notes,
    )

    missing = extract_missing_information(
        research_summary,
        publication_notes,
    )

    human_review = extract_human_review_items(
        research_summary,
        publication_notes,
    )

    excluded = extract_excluded_claims(
        publication_notes
    )

    link_problems = extract_link_problems(
        research_summary
    )

    sources = extract_sources(
        researched
    )

    identity = get_object(
        publishable,
        "identity",
    )

    title = clean_text(
        identity.get("title")
    ) or "Untitled Opportunity"

    lines: list[str] = [
        "<!-- enchanted-map-review-report -->",
        f"# ð§­ Moderator Review: {markdown_escape(title)}",
        "",
        (
            "This report compares the original submission, "
            "official-source research, and the proposed public quest page."
        ),
        "",
        (
            "**Nothing in this report is automatically verified or approved.** "
            "A human moderator must review the evidence and proposed wording."
        ),
        "",
    ]

    add_metadata_table(
        lines,
        researched,
        publishable,
    )

    add_bullet_section(
        lines,
        "â Confirmed",
        confirmed,
        empty_message=(
            "No fields were explicitly listed as confirmed "
            "by the research stage."
        ),
    )

    add_bullet_section(
        lines,
        "â ï¸ Possible Conflicts",
        conflicts,
        empty_message="No possible conflicts were reported.",
    )

    add_bullet_section(
        lines,
        "ð§© Important Information Not Found",
        missing,
        empty_message=(
            "No important missing information was reported."
        ),
    )

    add_bullet_section(
        lines,
        "ð Requires Human Judgment",
        human_review,
        empty_message=(
            "No additional human-judgment items were reported."
        ),
    )

    add_bullet_section(
        lines,
        "ð« Claims Excluded From the Public Draft",
        excluded,
        empty_message=(
            "No claims were explicitly excluded from the draft."
        ),
    )

    add_bullet_section(
        lines,
        "ð Incorrect or Outdated Links",
        link_problems,
        empty_message=(
            "No incorrect or outdated links were reported."
        ),
    )

    add_source_section(
        lines,
        sources,
    )

    add_checklist(
        lines,
        publishable,
    )

    lines.extend(
        [
            "---",
            "",
            (
                f"Generated at "
                f"{datetime.now(timezone.utc).isoformat()}."
            ),
            "",
        ]
    )

    return "\n".join(lines).rstrip() + "\n"


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    researched = read_json(
        RESEARCHED_SUBMISSION_FILE
    )

    publishable = read_json(
        PUBLISHABLE_CONTENT_FILE
    )

    validate_inputs(
        researched,
        publishable,
    )

    report = build_report(
        researched,
        publishable,
    )

    REVIEW_REPORT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    REVIEW_REPORT_FILE.write_text(
        report,
        encoding="utf-8",
    )

    write_github_output(
        "review_report_file",
        str(REVIEW_REPORT_FILE),
    )

    write_github_output(
        "moderator_report_file",
        str(REVIEW_REPORT_FILE),
    )

    print(
        "Moderator review report generated successfully."
    )
    print(
        f"Review report: {REVIEW_REPORT_FILE}"
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
