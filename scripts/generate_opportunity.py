from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


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

OPPORTUNITIES_DIRECTORY = Path(
    os.environ.get(
        "OPPORTUNITIES_DIRECTORY",
        "opportunities",
    )
)

MAX_TITLE_LENGTH = 300
MAX_SECTION_LENGTH = 20_000
MAX_LIST_ITEMS = 100
MAX_TAGS = 20

ALLOWED_SCHEMES = {"http", "https"}

ALLOWED_CATEGORIES = {
    "conference",
    "hackathon",
    "competition",
    "fellowship",
    "academy",
    "scholarship",
    "research-program",
    "exchange-program",
    "summer-school",
    "internship",
    "workshop-seminar",
    "bootcamp",
    "startup-program",
    "grant",
    "volunteering-program",
    "leadership-program",
    "cultural-program",
    "other",
}

ALLOWED_FORMATS = {
    "in-person",
    "online",
    "hybrid",
    "travelling",
    "multiple-formats",
    "not-confirmed",
}


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


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode(
        "ascii",
        "ignore",
    ).decode("ascii")

    ascii_value = ascii_value.lower()
    ascii_value = re.sub(
        r"[^a-z0-9]+",
        "-",
        ascii_value,
    )

    return ascii_value.strip("-")


def clean_scalar(
    value: Any,
    *,
    maximum: int = MAX_SECTION_LENGTH,
) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        value = str(value)

    value = value.strip()

    if not value:
        return None

    if len(value) > maximum:
        warn(
            f"A generated text value exceeded {maximum} characters "
            "and was truncated."
        )
        value = value[:maximum].rstrip() + "â¦"

    return value


def clean_string_list(
    value: Any,
    *,
    maximum: int = MAX_LIST_ITEMS,
) -> list[str]:
    if not isinstance(value, list):
        return []

    seen: set[str] = set()
    result: list[str] = []

    for item in value:
        cleaned = clean_scalar(item)

        if not cleaned:
            continue

        key = cleaned.casefold()

        if key in seen:
            continue

        seen.add(key)
        result.append(cleaned)

        if len(result) >= maximum:
            break

    return result


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


def markdown_escape_inline(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def markdown_link(label: str, url: str) -> str:
    safe_label = markdown_escape_inline(label)
    return f"[{safe_label}]({url})"


def yaml_safe_dump(data: dict[str, Any]) -> str:
    return yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=1000,
    ).strip()


# ============================================================
# INPUT VALIDATION
# ============================================================

def require_object(
    parent: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    value = parent.get(key)

    if not isinstance(value, dict):
        fail(f"'{key}' must be a JSON object.")

    return value


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

    moderation = require_object(
        publishable,
        "moderation",
    )

    if moderation.get("human_review_required") is not True:
        fail(
            "Publishable draft must require human review."
        )


# ============================================================
# STRUCTURED DATA EXTRACTION
# ============================================================

def value_from(
    parent: dict[str, Any],
    key: str,
) -> Any:
    return parent.get(key)


def normalized_date(
    dates: dict[str, Any],
    key: str,
) -> dict[str, str | None]:
    value = dates.get(key)

    if not isinstance(value, dict):
        return {
            "display": None,
            "normalized": None,
        }

    return {
        "display": clean_scalar(value.get("display")),
        "normalized": clean_scalar(
            value.get("normalized"),
            maximum=20,
        ),
    }


def build_front_matter(
    researched: dict[str, Any],
    publishable: dict[str, Any],
    slug: str,
) -> dict[str, Any]:
    identity = require_object(
        publishable,
        "identity",
    )

    location = require_object(
        publishable,
        "location",
    )

    dates = require_object(
        publishable,
        "dates",
    )

    eligibility = require_object(
        publishable,
        "eligibility",
    )

    audience = require_object(
        publishable,
        "audience",
    )

    funding = require_object(
        publishable,
        "funding",
    )

    application = require_object(
        publishable,
        "application",
    )

    program = require_object(
        publishable,
        "program",
    )

    filters = require_object(
        publishable,
        "filters",
    )

    moderation = require_object(
        publishable,
        "moderation",
    )

    category = clean_scalar(
        identity.get("category"),
        maximum=100,
    ) or "other"

    if category not in ALLOWED_CATEGORIES:
        category = "other"

    opportunity_format = clean_scalar(
        location.get("format"),
        maximum=100,
    ) or "not-confirmed"

    if opportunity_format not in ALLOWED_FORMATS:
        opportunity_format = "not-confirmed"

    application_deadline = normalized_date(
        dates,
        "application_deadline",
    )

    start_date = normalized_date(
        dates,
        "start_date",
    )

    end_date = normalized_date(
        dates,
        "end_date",
    )

    official_page = safe_url(
        application.get("official_page")
    )

    application_page = safe_url(
        application.get("application_page")
    )

    research_summary = researched.get(
        "research_summary",
        {},
    )

    if not isinstance(research_summary, dict):
        research_summary = {}

    research_provenance = researched.get(
        "provenance",
        {},
    )

    if not isinstance(research_provenance, dict):
        research_provenance = {}

    publication_provenance = publishable.get(
        "provenance",
        {},
    )

    if not isinstance(publication_provenance, dict):
        publication_provenance = {}

    raw_deadline = None
    researched_dates = researched.get("dates")

    if isinstance(researched_dates, dict):
        raw_deadline_object = researched_dates.get(
            "application_deadline"
        )

        if isinstance(raw_deadline_object, dict):
            raw_deadline = clean_scalar(
                raw_deadline_object.get("raw")
            )

    return {
        "schema_version": 1,
        "slug": slug,
        "title": clean_scalar(
            identity.get("title"),
            maximum=MAX_TITLE_LENGTH,
        ),
        "organizer": clean_scalar(
            identity.get("organizer"),
            maximum=MAX_TITLE_LENGTH,
        ),
        "category": category,
        "edition": clean_scalar(
            identity.get("edition"),
            maximum=100,
        ),
        "status": "pending-review",
        "summary": clean_scalar(
            publishable.get("summary")
        ),
        "format": opportunity_format,
        "location": {
            "display": clean_scalar(
                location.get("display")
            ),
            "host_city": clean_scalar(
                location.get("host_city"),
                maximum=200,
            ),
            "host_country": clean_scalar(
                location.get("host_country"),
                maximum=200,
            ),
            "host_country_code": clean_scalar(
                location.get("host_country_code"),
                maximum=10,
            ),
            "additional_locations": clean_string_list(
                location.get("additional_locations")
            ),
        },
        "dates": {
            "application_deadline": {
                "raw": raw_deadline,
                "display": application_deadline["display"],
                "normalized": application_deadline["normalized"],
            },
            "start_date": start_date,
            "end_date": end_date,
            "additional_dates": dates.get(
                "additional_dates",
                [],
            )
            if isinstance(
                dates.get("additional_dates"),
                list,
            )
            else [],
        },
        "eligibility": {
            "geographic_regions": clean_string_list(
                eligibility.get("geographic_regions")
            ),
            "eligible_countries": clean_string_list(
                eligibility.get("eligible_countries")
            ),
            "nationality_or_residency_rules": clean_scalar(
                eligibility.get(
                    "nationality_or_residency_rules"
                )
            ),
            "academic_levels": clean_string_list(
                eligibility.get("academic_levels")
            ),
            "broad_fields": clean_string_list(
                eligibility.get("broad_fields")
            ),
            "specific_majors": clean_string_list(
                eligibility.get("specific_majors")
            ),
            "age_requirements": clean_scalar(
                eligibility.get("age_requirements")
            ),
            "experience_requirements": clean_scalar(
                eligibility.get(
                    "experience_requirements"
                )
            ),
            "language_requirements": clean_scalar(
                eligibility.get("language_requirements")
            ),
        },
        "audience": {
            "groups": audience.get("groups", [])
            if isinstance(audience.get("groups"), list)
            else [],
        },
        "funding": {
            "application_fee": clean_scalar(
                funding.get("application_fee")
            ),
            "participation_fee": clean_scalar(
                funding.get("participation_fee")
            ),
            "scholarship": clean_scalar(
                funding.get("scholarship")
            ),
            "travel_support": clean_scalar(
                funding.get("travel_support")
            ),
            "accommodation": clean_scalar(
                funding.get("accommodation")
            ),
            "meals": clean_scalar(
                funding.get("meals")
            ),
            "stipend": clean_scalar(
                funding.get("stipend")
            ),
            "salary": clean_scalar(
                funding.get("salary")
            ),
            "prizes": clean_scalar(
                funding.get("prizes")
            ),
            "visa_support": clean_scalar(
                funding.get("visa_support")
            ),
            "accessibility_support": clean_scalar(
                funding.get("accessibility_support")
            ),
            "other_support": clean_string_list(
                funding.get("other_support")
            ),
        },
        "application": {
            "official_page": official_page,
            "application_page": application_page,
            "requirements": clean_string_list(
                application.get("requirements")
            ),
            "documents": clean_string_list(
                application.get("documents")
            ),
            "selection_process": clean_string_list(
                application.get("selection_process")
            ),
        },
        "program": {
            "activities": clean_string_list(
                program.get("activities")
            ),
            "benefits": clean_string_list(
                program.get("benefits")
            ),
            "topics": clean_string_list(
                program.get("topics")
            ),
        },
        "filters": {
            key: clean_string_list(filters.get(key))
            for key in (
                "categories",
                "formats",
                "host_countries",
                "eligible_regions",
                "eligible_countries",
                "academic_levels",
                "academic_fields",
                "audience_groups",
                "funding_features",
                "topics",
            )
        },
        "tags": clean_string_list(
            publishable.get("tags"),
            maximum=MAX_TAGS,
        ),
        "verification": {
            "human_review_required": True,
            "safe_to_generate_draft_page": bool(
                moderation.get(
                    "safe_to_generate_draft_page",
                    False,
                )
            ),
            "research_confidence": research_summary.get(
                "overall_confidence",
                0,
            ),
            "research_recommended_action": (
                research_summary.get(
                    "recommended_action"
                )
            ),
            "formatter_recommended_action": (
                moderation.get(
                    "recommended_action"
                )
            ),
            "automatically_verified": False,
        },
        "submission": {
            "issue_number": ISSUE_NUMBER,
            "issue_url": research_provenance.get(
                "original_issue_url"
            ),
        },
        "provenance": {
            "research_model": research_provenance.get(
                "research_model"
            ),
            "formatter_model": publication_provenance.get(
                "formatter_model"
            ),
            "researched_at": research_provenance.get(
                "researched_at"
            ),
            "formatted_at": publication_provenance.get(
                "formatted_at"
            ),
            "generated_at": datetime.now(
                timezone.utc
            ).isoformat(),
        },
    }


# ============================================================
# MARKDOWN GENERATION
# ============================================================

def add_text_section(
    lines: list[str],
    heading: str,
    text: Any,
) -> None:
    cleaned = clean_scalar(text)

    if not cleaned:
        return

    lines.extend(
        [
            f"## {heading}",
            "",
            cleaned,
            "",
        ]
    )


def add_bullet_section(
    lines: list[str],
    heading: str,
    values: Any,
) -> None:
    items = clean_string_list(values)

    if not items:
        return

    lines.extend(
        [
            f"## {heading}",
            "",
        ]
    )

    lines.extend(
        f"- {item}"
        for item in items
    )

    lines.append("")


def add_portals_section(
    lines: list[str],
    official_page: str | None,
    application_page: str | None,
) -> None:
    if not official_page and not application_page:
        return

    lines.extend(
        [
            "## ð Official Portals",
            "",
        ]
    )

    if official_page:
        lines.append(
            f"- {markdown_link('Official opportunity page', official_page)}"
        )

    if application_page:
        lines.append(
            f"- {markdown_link('Direct application page', application_page)}"
        )

    lines.append("")


def build_markdown_body(
    front_matter: dict[str, Any],
    publishable: dict[str, Any],
) -> str:
    identity = require_object(
        publishable,
        "identity",
    )

    quest_content = require_object(
        publishable,
        "quest_content",
    )

    application = require_object(
        publishable,
        "application",
    )

    title = clean_scalar(
        identity.get("title"),
        maximum=MAX_TITLE_LENGTH,
    ) or "Untitled Opportunity"

    summary = clean_scalar(
        publishable.get("summary")
    )

    lines: list[str] = [
        f"# ðºï¸ {title}",
        "",
    ]

    if summary:
        lines.extend(
            [
                f"> {summary}",
                "",
            ]
        )

    add_text_section(
        lines,
        "âï¸ The Quest",
        quest_content.get("quest"),
    )

    add_text_section(
        lines,
        "ð° The Organizer",
        quest_content.get("organizer"),
    )

    add_text_section(
        lines,
        "ð Who May Enter",
        quest_content.get("who_may_enter"),
    )

    add_text_section(
        lines,
        "ð Quest Location",
        quest_content.get("quest_location"),
    )

    add_text_section(
        lines,
        "â³ Important Dates",
        quest_content.get("important_dates"),
    )

    add_text_section(
        lines,
        "ð° Rewards and Support",
        quest_content.get("rewards_and_support"),
    )

    add_text_section(
        lines,
        "ð¹ Application Path",
        quest_content.get("application_path"),
    )

    add_text_section(
        lines,
        "ð§­ What Participants Do",
        quest_content.get("what_participants_do"),
    )

    add_portals_section(
        lines,
        safe_url(application.get("official_page")),
        safe_url(application.get("application_page")),
    )

    issue_url = (
        front_matter.get("submission", {})
        .get("issue_url")
        if isinstance(
            front_matter.get("submission"),
            dict,
        )
        else None
    )

    if safe_url(issue_url):
        lines.extend(
            [
                "---",
                "",
                "### ð¡ï¸ Review trail",
                "",
                (
                    "This quest was prepared from a community submission, "
                    "official-source research, and human review."
                ),
                "",
                f"- {markdown_link('View the original submission', issue_url)}",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def create_opportunity_file(
    researched: dict[str, Any],
    publishable: dict[str, Any],
) -> tuple[Path, str, str]:
    identity = require_object(
        publishable,
        "identity",
    )

    title = clean_scalar(
        identity.get("title"),
        maximum=MAX_TITLE_LENGTH,
    )

    if not title:
        fail(
            "Cannot generate an opportunity page without a title."
        )

    category = clean_scalar(
        identity.get("category"),
        maximum=100,
    ) or "other"

    if category not in ALLOWED_CATEGORIES:
        category = "other"

    slug = slugify(title)

    if not slug:
        slug = f"opportunity-{ISSUE_NUMBER}"

    # Add the issue number only when an existing file would be overwritten.
    category_directory = (
        OPPORTUNITIES_DIRECTORY
        / category
    )

    category_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = category_directory / f"{slug}.md"

    if output_file.exists():
        slug = f"{slug}-{ISSUE_NUMBER}"
        output_file = (
            category_directory
            / f"{slug}.md"
        )

    front_matter = build_front_matter(
        researched,
        publishable,
        slug,
    )

    body = build_markdown_body(
        front_matter,
        publishable,
    )

    content = (
        "---\n"
        f"{yaml_safe_dump(front_matter)}\n"
        "---\n\n"
        f"{body}"
    )

    output_file.write_text(
        content,
        encoding="utf-8",
    )

    return output_file, category, slug


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

    output_file, category, slug = (
        create_opportunity_file(
            researched,
            publishable,
        )
    )

    write_github_output(
        "opportunity_file",
        str(output_file),
    )

    write_github_output(
        "category",
        category,
    )

    write_github_output(
        "slug",
        slug,
    )

    write_github_output(
        "generated_opportunity_file",
        str(output_file),
    )

    print(
        "Opportunity Markdown page generated successfully."
    )
    print(
        f"Output file: {output_file}"
    )
    print(
        f"Category: {category}"
    )
    print(
        f"Slug: {slug}"
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
