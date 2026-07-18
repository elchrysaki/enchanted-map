from __future__ import annotations

import html
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

MAX_ITEMS = 100
MAX_TEXT_LENGTH = 10_000
MAX_URL_LENGTH = 2_000

ALLOWED_ACTIONS = {
    "continue-to-draft-pr",
    "manual-formatting-needed",
    "request-more-information",
    "hold-for-human-review",
}


# ============================================================
# ERRORS AND BASIC HELPERS
# ============================================================

def fail(message: str) -> None:
    print(f"::error::{message}")
    raise SystemExit(1)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        fail(f"Required JSON file not found: {path}")

    try:
        value = json.loads(
            path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        fail(f"Invalid JSON in {path}: {exc}")

    if not isinstance(value, dict):
        fail(f"Expected a JSON object in {path}")

    return value


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


def require_object(
    parent: dict[str, Any],
    key: str,
    *,
    context: str,
) -> dict[str, Any]:
    value = parent.get(key)

    if not isinstance(value, dict):
        fail(
            f"{context}: '{key}' must be a JSON object."
        )

    return value


def require_list(
    parent: dict[str, Any],
    key: str,
    *,
    context: str,
) -> list[Any]:
    value = parent.get(key)

    if not isinstance(value, list):
        fail(
            f"{context}: '{key}' must be a JSON list."
        )

    return value


def clean_text(
    value: Any,
    field_name: str,
    *,
    required: bool = False,
    maximum: int = MAX_TEXT_LENGTH,
) -> str | None:
    if value is None:
        if required:
            fail(f"'{field_name}' must contain text.")

        return None

    if not isinstance(value, str):
        fail(
            f"'{field_name}' must be a string or null."
        )

    cleaned = value.strip()

    if not cleaned:
        if required:
            fail(f"'{field_name}' must contain text.")

        return None

    if len(cleaned) > maximum:
        fail(
            f"'{field_name}' exceeds "
            f"{maximum} characters."
        )

    return cleaned


def clean_string_list(
    value: Any,
    field_name: str,
    *,
    maximum: int = MAX_ITEMS,
) -> list[str]:
    if not isinstance(value, list):
        fail(
            f"'{field_name}' must be a JSON list."
        )

    if len(value) > maximum:
        fail(
            f"'{field_name}' contains more than "
            f"{maximum} values."
        )

    result: list[str] = []

    for index, item in enumerate(value):
        cleaned = clean_text(
            item,
            f"{field_name}[{index}]",
            required=True,
        )

        if cleaned is None:
            fail(
                f"'{field_name}[{index}]' "
                "must contain text."
            )

        result.append(cleaned)

    return result


def safe_url(
    value: Any,
    field_name: str,
) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        fail(
            f"'{field_name}' must be a string or null."
        )

    candidate = value.strip()

    if not candidate:
        fail(
            f"'{field_name}' must not be empty."
        )

    if len(candidate) > MAX_URL_LENGTH:
        fail(
            f"'{field_name}' exceeds the URL length limit."
        )

    if any(
        character in candidate
        for character in (
            "\r",
            "\n",
            "\t",
            " ",
            "<",
            ">",
            '"',
        )
    ):
        fail(
            f"'{field_name}' contains unsafe URL characters."
        )

    try:
        parsed = urlparse(candidate)
        port = parsed.port
    except ValueError as exc:
        fail(
            f"'{field_name}' is not a valid URL: {exc}"
        )

    if parsed.scheme.lower() not in {
        "http",
        "https",
    }:
        fail(
            f"'{field_name}' must use HTTP or HTTPS."
        )

    if not parsed.hostname:
        fail(
            f"'{field_name}' must include a hostname."
        )

    if parsed.username or parsed.password:
        fail(
            f"'{field_name}' must not contain credentials."
        )

    if port not in (
        None,
        80,
        443,
    ):
        fail(
            f"'{field_name}' must not use "
            "a non-standard port."
        )

    return candidate


def neutralize_mentions(value: str) -> str:
    return value.replace(
        "@",
        "@\u200b",
    )


def markdown_text(value: str) -> str:
    escaped = html.escape(
        neutralize_mentions(value),
        quote=False,
    )

    for source, replacement in (
        ("\\", "\\\\"),
        ("`", "\\`"),
        ("*", "\\*"),
        ("_", "\\_"),
        ("[", "\\["),
        ("]", "\\]"),
        ("|", "\\|"),
    ):
        escaped = escaped.replace(
            source,
            replacement,
        )

    return escaped


def markdown_inline(value: str) -> str:
    return markdown_text(
        " ".join(value.split())
    )


def markdown_link(
    label: str,
    url: str,
) -> str:
    return (
        f"[{markdown_inline(label)}]"
        f"(<{url}>)"
    )


def unique_strings(
    values: list[str],
) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        cleaned = " ".join(
            value.split()
        )

        if not cleaned:
            continue

        key = cleaned.casefold()

        if key in seen:
            continue

        seen.add(key)
        result.append(cleaned)

        if len(result) >= MAX_ITEMS:
            break

    return result


def display_list(
    values: list[str],
) -> str:
    if not values:
        return "None selected"

    return ", ".join(
        f"`{markdown_inline(item)}`"
        for item in values
    )


# ============================================================
# INPUT VALIDATION
# ============================================================

def validate_issue_number(
    record: dict[str, Any],
    *,
    context: str,
) -> None:
    value = record.get("issue_number")

    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value != ISSUE_NUMBER
    ):
        fail(
            f"{context}: issue_number does not "
            "match ISSUE_NUMBER."
        )


def validate_inputs(
    researched: dict[str, Any],
    publishable: dict[str, Any],
) -> None:
    if researched.get("schema_version") != 2:
        fail(
            "Research input must use schema version 2."
        )

    if (
        researched.get("record_type")
        != "researched-submission"
    ):
        fail(
            "Research input is not a "
            "researched-submission record."
        )

    if publishable.get("schema_version") != 2:
        fail(
            "Publishable input must use schema version 2."
        )

    if (
        publishable.get("record_type")
        != "publishable-opportunity-draft"
    ):
        fail(
            "Publishable input is not a "
            "publishable-opportunity-draft record."
        )

    validate_issue_number(
        researched,
        context="Research input",
    )

    validate_issue_number(
        publishable,
        context="Publishable input",
    )

    identity = require_object(
        publishable,
        "identity",
        context="Publishable input",
    )

    title = clean_text(
        identity.get("title"),
        "identity.title",
        required=True,
        maximum=300,
    )

    main_category = clean_text(
        identity.get("main_category"),
        "identity.main_category",
        required=True,
        maximum=100,
    )

    category = clean_text(
        identity.get("category"),
        "identity.category",
        required=True,
        maximum=100,
    )

    if (
        title is None
        or main_category is None
        or category is None
    ):
        fail(
            "Publishable identity is incomplete."
        )

    researched_audience = require_object(
        researched,
        "audience",
        context="Research input",
    )

    publishable_audience = require_object(
        publishable,
        "audience",
        context="Publishable input",
    )

    for context, audience in (
        (
            "Research",
            researched_audience,
        ),
        (
            "Publishable",
            publishable_audience,
        ),
    ):
        if (
            audience.get(
                "classification_source"
            )
            != "submitted-dropdown-only"
        ):
            fail(
                f"{context} audience "
                "classification_source must be "
                "'submitted-dropdown-only'."
            )

    researched_groups = clean_string_list(
        require_list(
            researched_audience,
            "groups",
            context="Research input audience",
        ),
        "researched.audience.groups",
    )

    publishable_groups = clean_string_list(
        require_list(
            publishable_audience,
            "groups",
            context="Publishable input audience",
        ),
        "publishable.audience.groups",
    )

    if publishable_groups != researched_groups:
        fail(
            "Publishable audience groups must exactly "
            "match the researched submitted-dropdown "
            "groups, including order."
        )

    filters = require_object(
        publishable,
        "filters",
        context="Publishable input",
    )

    main_category_filters = clean_string_list(
        require_list(
            filters,
            "main_categories",
            context="Publishable filters",
        ),
        "filters.main_categories",
    )

    category_filters = clean_string_list(
        require_list(
            filters,
            "categories",
            context="Publishable filters",
        ),
        "filters.categories",
    )

    audience_filters = clean_string_list(
        require_list(
            filters,
            "audience_groups",
            context="Publishable filters",
        ),
        "filters.audience_groups",
    )

    if main_category_filters != [
        main_category
    ]:
        fail(
            "filters.main_categories must exactly equal "
            "[identity.main_category]."
        )

    if category_filters != [
        category
    ]:
        fail(
            "filters.categories must exactly equal "
            "[identity.category]."
        )

    if audience_filters != publishable_groups:
        fail(
            "filters.audience_groups must exactly "
            "match audience.groups, including order."
        )

    moderation = require_object(
        publishable,
        "moderation",
        context="Publishable input",
    )

    if (
        moderation.get(
            "human_review_required"
        )
        is not True
    ):
        fail(
            "The publishable draft must require "
            "human review."
        )

    safe_to_generate = moderation.get(
        "safe_to_generate_draft_page"
    )

    if not isinstance(
        safe_to_generate,
        bool,
    ):
        fail(
            "moderation.safe_to_generate_draft_page "
            "must be a boolean."
        )

    action = moderation.get(
        "recommended_action"
    )

    if action not in ALLOWED_ACTIONS:
        fail(
            "Invalid formatter recommended action: "
            f"{action}"
        )

    if (
        safe_to_generate is False
        and action == "continue-to-draft-pr"
    ):
        fail(
            "An unsafe draft cannot recommend "
            "continue-to-draft-pr."
        )

    require_object(
        researched,
        "research_summary",
        context="Research input",
    )

    require_object(
        researched,
        "provenance",
        context="Research input",
    )

    require_object(
        publishable,
        "publication_notes",
        context="Publishable input",
    )

    if OPPORTUNITY_FILE is not None:
        if OPPORTUNITY_FILE.is_absolute():
            fail(
                "OPPORTUNITY_FILE must be "
                "repository-relative."
            )

        if not OPPORTUNITY_FILE.exists():
            fail(
                "OPPORTUNITY_FILE does not exist: "
                f"{OPPORTUNITY_FILE}"
            )

        if OPPORTUNITY_FILE.is_symlink():
            fail(
                "OPPORTUNITY_FILE must not be "
                "a symbolic link."
            )

        if (
            not safe_to_generate
            or action
            != "continue-to-draft-pr"
        ):
            fail(
                "An opportunity file was provided "
                "for a record that is not cleared "
                "for a draft PR."
            )


# ============================================================
# RESEARCH SUMMARY EXTRACTION
# ============================================================

def normalize_summary_items(
    values: Any,
) -> list[str]:
    if not isinstance(values, list):
        return []

    result: list[str] = []

    for item in values:
        if isinstance(item, str):
            cleaned = item.strip()

            if cleaned:
                result.append(cleaned)

            continue

        if not isinstance(item, dict):
            continue

        field = clean_text(
            item.get("field"),
            "research summary item.field",
        )

        message: str | None = None

        for key in (
            "message",
            "finding",
            "researched_claim",
            "recommended_moderator_action",
            "reason",
        ):
            message = clean_text(
                item.get(key),
                f"research summary item.{key}",
            )

            if message:
                break

        if field and message:
            result.append(
                f"{field}: {message}"
            )
        elif message:
            result.append(message)
        elif field:
            result.append(field)

    return unique_strings(result)


def combined_items(
    first: dict[str, Any],
    first_keys: tuple[str, ...],
    second: dict[str, Any] | None = None,
    second_keys: tuple[str, ...] = (),
) -> list[str]:
    result: list[str] = []

    for key in first_keys:
        result.extend(
            normalize_summary_items(
                first.get(key)
            )
        )

    if second is not None:
        for key in second_keys:
            result.extend(
                normalize_summary_items(
                    second.get(key)
                )
            )

    return unique_strings(result)


def extract_sources(
    researched: dict[str, Any],
) -> list[dict[str, str]]:
    summary = require_object(
        researched,
        "research_summary",
        context="Research input",
    )

    source_items = summary.get(
        "sources_checked",
        [],
    )

    if not isinstance(
        source_items,
        list,
    ):
        return []

    sources: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for index, item in enumerate(
        source_items
    ):
        if isinstance(item, str):
            url = safe_url(
                item,
                (
                    "research_summary."
                    f"sources_checked[{index}]"
                ),
            )

            label = "Source"

        elif isinstance(item, dict):
            url = safe_url(
                (
                    item.get("url")
                    or item.get("final_url")
                ),
                (
                    "research_summary."
                    f"sources_checked[{index}].url"
                ),
            )

            label = (
                clean_text(
                    item.get("page_title"),
                    "research source.page_title",
                )
                or clean_text(
                    item.get("source_type"),
                    "research source.source_type",
                )
                or clean_text(
                    item.get("title"),
                    "research source.title",
                )
                or "Source"
            )

        else:
            continue

        if (
            not url
            or url in seen_urls
        ):
            continue

        seen_urls.add(url)

        sources.append(
            {
                "label": label,
                "url": url,
            }
        )

        if len(sources) >= MAX_ITEMS:
            break

    return sources


# ============================================================
# REPORT SECTIONS
# ============================================================

def add_bullet_section(
    lines: list[str],
    heading: str,
    items: list[str],
    empty_message: str,
) -> None:
    lines.extend(
        [
            f"## {heading}",
            "",
        ]
    )

    if items:
        lines.extend(
            f"- {markdown_inline(item)}"
            for item in items
        )
    else:
        lines.append(
            f"- {markdown_inline(empty_message)}"
        )

    lines.append("")


def add_source_section(
    lines: list[str],
    sources: list[dict[str, str]],
) -> None:
    lines.extend(
        [
            "## 🔗 Sources Checked",
            "",
        ]
    )

    if not sources:
        lines.append(
            "- No source list was returned "
            "by the research stage."
        )
    else:
        for source in sources:
            lines.append(
                "- "
                + markdown_link(
                    source["label"],
                    source["url"],
                )
            )

    lines.append("")


def add_snapshot(
    lines: list[str],
    researched: dict[str, Any],
    publishable: dict[str, Any],
) -> None:
    identity = require_object(
        publishable,
        "identity",
        context="Publishable input",
    )

    audience = require_object(
        publishable,
        "audience",
        context="Publishable input",
    )

    moderation = require_object(
        publishable,
        "moderation",
        context="Publishable input",
    )

    summary = require_object(
        researched,
        "research_summary",
        context="Research input",
    )

    provenance = require_object(
        researched,
        "provenance",
        context="Research input",
    )

    title = clean_text(
        identity.get("title"),
        "identity.title",
        required=True,
        maximum=300,
    )

    main_category = clean_text(
        identity.get("main_category"),
        "identity.main_category",
        required=True,
        maximum=100,
    )

    category = clean_text(
        identity.get("category"),
        "identity.category",
        required=True,
        maximum=100,
    )

    groups = clean_string_list(
        audience.get("groups"),
        "audience.groups",
    )

    confidence = summary.get(
        "overall_confidence",
        0,
    )

    if (
        not isinstance(confidence, int)
        or isinstance(confidence, bool)
        or not 0 <= confidence <= 100
    ):
        confidence = 0

    research_action = (
        clean_text(
            summary.get(
                "recommended_action"
            ),
            (
                "research_summary."
                "recommended_action"
            ),
            maximum=100,
        )
        or "not provided"
    )

    formatter_action = clean_text(
        moderation.get(
            "recommended_action"
        ),
        "moderation.recommended_action",
        required=True,
        maximum=100,
    )

    safe_to_generate = moderation[
        "safe_to_generate_draft_page"
    ]

    lines.extend(
        [
            "## 🧾 Review Snapshot",
            "",
            "| Field | Value |",
            "|---|---|",
            (
                "| Opportunity | "
                f"{markdown_inline(title or '')} |"
            ),
            (
                "| Main category | "
                f"`{markdown_inline(main_category or '')}` |"
            ),
            (
                "| Specific category | "
                f"`{markdown_inline(category or '')}` |"
            ),
            (
                "| Audience source | "
                "`submitted-dropdown-only` |"
            ),
            (
                "| Audience groups | "
                f"{display_list(groups)} |"
            ),
            (
                "| Research confidence | "
                f"`{confidence}` |"
            ),
            (
                "| Research action | "
                f"`{markdown_inline(research_action)}` |"
            ),
            (
                "| Formatter action | "
                f"`{markdown_inline(formatter_action or '')}` |"
            ),
            (
                "| Safe to generate draft page | "
                f"`{str(safe_to_generate).lower()}` |"
            ),
        ]
    )

    issue_url = safe_url(
        provenance.get(
            "original_issue_url"
        ),
        "provenance.original_issue_url",
    )

    if issue_url:
        lines.append(
            "| Original issue | "
            + markdown_link(
                "Open submission",
                issue_url,
            )
            + " |"
        )

    if OPPORTUNITY_FILE is None:
        lines.append(
            "| Proposed opportunity page | "
            "Not generated |"
        )
    else:
        lines.append(
            "| Proposed opportunity page | "
            f"`{markdown_inline(str(OPPORTUNITY_FILE))}` |"
        )

    lines.append("")


def add_classification_guardrails(
    lines: list[str],
    researched: dict[str, Any],
    publishable: dict[str, Any],
    audience_flags: list[str],
) -> None:
    researched_audience = require_object(
        researched,
        "audience",
        context="Research input",
    )

    publishable_audience = require_object(
        publishable,
        "audience",
        context="Publishable input",
    )

    filters = require_object(
        publishable,
        "filters",
        context="Publishable input",
    )

    researched_groups = clean_string_list(
        researched_audience.get("groups"),
        "researched.audience.groups",
    )

    publishable_groups = clean_string_list(
        publishable_audience.get("groups"),
        "publishable.audience.groups",
    )

    filter_groups = clean_string_list(
        filters.get("audience_groups"),
        "filters.audience_groups",
    )

    lines.extend(
        [
            "## 🧭 Classification Guardrails",
            "",
            (
                "- `main_category` and `category` "
                "are separate classifications and "
                "must be reviewed separately."
            ),
            (
                "- Audience groups come only from "
                "the submitter's dropdown selections."
            ),
            (
                "- Research may flag unsupported "
                "selected groups, but it must not "
                "add, remove, or replace tags."
            ),
            (
                "- Researched groups: "
                f"{display_list(researched_groups)}"
            ),
            (
                "- Publishable groups: "
                f"{display_list(publishable_groups)}"
            ),
            (
                "- Filter groups: "
                f"{display_list(filter_groups)}"
            ),
        ]
    )

    if audience_flags:
        lines.extend(
            [
                "",
                "**Audience concerns:**",
                "",
            ]
        )

        lines.extend(
            f"- {markdown_inline(item)}"
            for item in audience_flags
        )

    lines.append("")


def add_checklist(
    lines: list[str],
    publishable: dict[str, Any],
) -> None:
    moderation = require_object(
        publishable,
        "moderation",
        context="Publishable input",
    )

    safe_to_generate = moderation[
        "safe_to_generate_draft_page"
    ]

    action = moderation[
        "recommended_action"
    ]

    lines.extend(
        [
            "## 🛡️ Human Review Checklist",
            "",
            (
                "- [ ] Confirm the opportunity "
                "and organizer."
            ),
            (
                "- [ ] Confirm `main_category` "
                "and `category` separately."
            ),
            (
                "- [ ] Open the official and "
                "application links."
            ),
            (
                "- [ ] Confirm deadline, dates, "
                "and edition."
            ),
            (
                "- [ ] Review geographic, academic, "
                "age, language, and experience "
                "requirements."
            ),
            (
                "- [ ] Confirm audience groups "
                "exactly match the submitted "
                "dropdown selections."
            ),
            (
                "- [ ] Do not infer audience groups "
                "from website prose, eligibility "
                "text, images, or model judgment."
            ),
            (
                "- [ ] Confirm fees, travel, "
                "accommodation, meals, scholarships, "
                "stipend or salary, prizes, and support."
            ),
            (
                "- [ ] Remove or rewrite unsupported "
                "public claims."
            ),
            (
                "- [ ] Confirm deterministic filters "
                "match their structured source fields."
            ),
        ]
    )

    if not safe_to_generate:
        lines.append(
            "- [ ] Resolve why the formatter "
            "marked the draft unsafe."
        )

    if action != "continue-to-draft-pr":
        lines.append(
            "- [ ] Resolve formatter recommendation "
            f"`{markdown_inline(action)}`."
        )

    lines.extend(
        [
            (
                "- [ ] Approve the final page "
                "for publication."
            ),
            "",
            (
                "> Merging remains a human decision. "
                "This report cannot approve or publish "
                "the opportunity."
            ),
            "",
        ]
    )


# ============================================================
# REPORT GENERATION
# ============================================================

def build_report(
    researched: dict[str, Any],
    publishable: dict[str, Any],
) -> str:
    summary = require_object(
        researched,
        "research_summary",
        context="Research input",
    )

    notes = require_object(
        publishable,
        "publication_notes",
        context="Publishable input",
    )

    moderation = require_object(
        publishable,
        "moderation",
        context="Publishable input",
    )

    identity = require_object(
        publishable,
        "identity",
        context="Publishable input",
    )

    title = clean_text(
        identity.get("title"),
        "identity.title",
        required=True,
        maximum=300,
    )

    confirmed = combined_items(
        summary,
        (
            "confirmed_fields",
        ),
    )

    clarified = combined_items(
        summary,
        (
            "confirmed_with_clarification",
        ),
    )

    confirmed.extend(
        (
            f"{item} "
            "(confirmed with clarification)"
        )
        for item in clarified
    )

    confirmed = unique_strings(
        confirmed
    )

    conflicts = combined_items(
        summary,
        (
            "possible_conflicts",
        ),
        notes,
        (
            "conflicts",
        ),
    )

    missing = combined_items(
        summary,
        (
            "important_information_not_found",
        ),
        notes,
        (
            "missing_information",
        ),
    )

    human_review = combined_items(
        summary,
        (
            "requires_human_judgment",
            "moderator_focus",
        ),
        notes,
        (
            "human_review",
        ),
    )

    excluded = combined_items(
        notes,
        (
            "excluded_claims",
        ),
    )

    link_problems = combined_items(
        summary,
        (
            "incorrect_or_outdated_links",
        ),
    )

    audience_flags = combined_items(
        summary,
        (
            "unsupported_audience_groups",
            "audience_review",
            "audience_flags",
        ),
        notes,
        (
            "unsupported_audience_groups",
            "audience_review",
        ),
    )

    safe_to_generate = moderation[
        "safe_to_generate_draft_page"
    ]

    action = moderation[
        "recommended_action"
    ]

    lines: list[str] = [
        (
            "# 🧭 Moderator Review: "
            f"{markdown_inline(title or '')}"
        ),
        "",
        (
            "This report compares the original "
            "submission, official-source research, "
            "and the proposed publishable OFFMAP record."
        ),
        "",
        (
            "**Nothing here is automatically verified "
            "or approved. A human moderator must review "
            "the evidence and wording.**"
        ),
        "",
    ]

    if (
        not safe_to_generate
        or action != "continue-to-draft-pr"
    ):
        lines.extend(
            [
                "> [!WARNING]",
                (
                    "> This record is on hold. "
                    "Do not create or merge a publication "
                    "page until the issues are resolved."
                ),
                "",
            ]
        )

    add_snapshot(
        lines,
        researched,
        publishable,
    )

    add_classification_guardrails(
        lines,
        researched,
        publishable,
        audience_flags,
    )

    add_bullet_section(
        lines,
        "✅ Confirmed",
        confirmed,
        (
            "No fields were explicitly listed "
            "as confirmed."
        ),
    )

    add_bullet_section(
        lines,
        "⚠️ Possible Conflicts",
        conflicts,
        (
            "No possible conflicts were reported."
        ),
    )

    add_bullet_section(
        lines,
        "🧩 Important Information Not Found",
        missing,
        (
            "No important missing information "
            "was reported."
        ),
    )

    add_bullet_section(
        lines,
        "🔍 Requires Human Judgment",
        human_review,
        (
            "No additional human-judgment items "
            "were reported."
        ),
    )

    add_bullet_section(
        lines,
        "🚫 Claims Excluded From the Public Draft",
        excluded,
        (
            "No claims were explicitly excluded "
            "from the draft."
        ),
    )

    add_bullet_section(
        lines,
        "🔗 Incorrect or Outdated Links",
        link_problems,
        (
            "No incorrect or outdated links "
            "were reported."
        ),
    )

    add_source_section(
        lines,
        extract_sources(researched),
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
                "Generated at "
                f"{datetime.now(timezone.utc).isoformat()}."
            ),
            "",
        ]
    )

    return "\n".join(lines)


# ============================================================
# OUTPUT
# ============================================================

def atomic_write(
    path: Path,
    content: str,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary.write_text(
        content,
        encoding="utf-8",
    )

    temporary.replace(path)


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

    atomic_write(
        REVIEW_REPORT_FILE,
        report,
    )

    moderation = publishable[
        "moderation"
    ]

    write_github_output(
        "review_report_file",
        str(REVIEW_REPORT_FILE),
    )

    write_github_output(
        "moderator_report_file",
        str(REVIEW_REPORT_FILE),
    )

    write_github_output(
        "safe_to_generate_draft_page",
        str(
            moderation[
                "safe_to_generate_draft_page"
            ]
        ).lower(),
    )

    write_github_output(
        "formatter_recommended_action",
        moderation[
            "recommended_action"
        ],
    )

    print(
        "OFFMAP moderator review report "
        "generated successfully."
    )

    print(
        f"Review report: {REVIEW_REPORT_FILE}"
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
