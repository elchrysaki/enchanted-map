import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml


ISSUE_NUMBER = os.environ["ISSUE_NUMBER"]

SUBMISSION_FILE = Path(
    os.environ.get(
        "SUBMISSION_FILE",
        f"artifacts/submission-{ISSUE_NUMBER}.json",
    )
)

AI_OUTPUT_FILE = Path(
    os.environ.get(
        "AI_OUTPUT_FILE",
        f"artifacts/ai-result-{ISSUE_NUMBER}.json",
    )
)

OPPORTUNITIES_DIRECTORY = Path(
    os.environ.get(
        "OPPORTUNITIES_DIRECTORY",
        "opportunities",
    )
)


def fail(message: str) -> None:
    print(f"::error::{message}")
    raise SystemExit(1)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        fail(f"Required file not found: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"Invalid JSON in {path}: {exc}")

    if not isinstance(data, dict):
        fail(f"Expected a JSON object in {path}")

    return data


def first_value(
    data: dict[str, Any],
    possible_keys: list[str],
    default: Any = "",
) -> Any:
    for key in possible_keys:
        value = data.get(key)

        if value not in (None, "", [], {}):
            return value

    return default


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, list):
        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]

    if isinstance(value, str):
        parts = re.split(r"[\n,;•]+", value)

        return [
            item.strip()
            for item in parts
            if item.strip()
        ]

    text = str(value).strip()
    return [text] if text else []


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


def clean_date(value: Any) -> str | None:
    if value in (
        None,
        "",
        "Not confirmed",
        "Not announced",
    ):
        return None

    return str(value).strip()


def clean_nullable_string(
    value: Any,
) -> str | None:
    if value in (
        None,
        "",
        "Not confirmed",
    ):
        return None

    return str(value).strip()


def yaml_front_matter(
    data: dict[str, Any],
) -> str:
    yaml_text = yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=100,
    ).strip()

    return f"---\n{yaml_text}\n---"


def build_front_matter(
    submission: dict[str, Any],
    ai_result: dict[str, Any],
) -> dict[str, Any]:
    display = ai_result.get("display", {})
    classification = ai_result.get(
        "classification",
        {},
    )
    moderation = ai_result.get(
        "moderation",
        {},
    )

    title = (
        display.get("official_name")
        or first_value(
            submission,
            [
                "opportunity_name",
                "Opportunity name",
                "title",
                "name",
            ],
            "Untitled Opportunity",
        )
    )

    category = (
        classification.get("category_slug")
        or first_value(
            submission,
            [
                "category",
                "Opportunity category",
                "Quest category",
            ],
            "other",
        )
    )

    category = (
        slugify(str(category))
        or "other"
    )

    slug = (
        slugify(str(title))
        or f"opportunity-{ISSUE_NUMBER}"
    )

    host_country = (
        classification.get(
            "host_country_normalized"
        )
        or first_value(
            submission,
            [
                "host_country",
                "Host country",
            ],
            "",
        )
    )

    host_city = first_value(
        submission,
        [
            "host_city",
            "Host city",
        ],
        "",
    )

    official_url = first_value(
        submission,
        [
            "official_website",
            "Official opportunity page",
            "official_link",
            "website",
        ],
        "",
    )

    application_url = first_value(
        submission,
        [
            "application_link",
            "Direct application portal",
        ],
        "",
    )

    organizer = first_value(
        submission,
        [
            "organizer",
            "Organizer",
        ],
        "",
    )

    opportunity_format = first_value(
        submission,
        [
            "opportunity_format",
            "Quest format",
            "format",
        ],
        "not-confirmed",
    )

    application_deadline = first_value(
        submission,
        [
            "application_deadline",
            "Application deadline",
            "deadline",
        ],
        "",
    )

    start_date = first_value(
        submission,
        [
            "start_date",
            "Start date",
        ],
        "",
    )

    end_date = first_value(
        submission,
        [
            "end_date",
            "End date",
        ],
        "",
    )

    eligible_countries = normalize_list(
        first_value(
            submission,
            [
                "eligible_countries",
                "Eligible countries",
            ],
            [],
        )
    )

    audience_access = (
        classification.get(
            "audience_access"
        )
        or first_value(
            submission,
            [
                "audience_access",
                "Audience access model",
            ],
            "not-confirmed",
        )
    )

    participation_fee = first_value(
        submission,
        [
            "participation_fee",
            "Application or participation fee",
        ],
        "Not confirmed",
    )

    return {
        "schema_version": 1,
        "id": f"{slug}-{ISSUE_NUMBER}",
        "title": str(title).strip(),
        "slug": slug,
        "category": category,
        "status": "pending-review",

        "organizer": clean_nullable_string(
            organizer
        ),

        "official_url": clean_nullable_string(
            official_url
        ),

        "application_url": clean_nullable_string(
            application_url
        ),

        "location": {
            "city": clean_nullable_string(
                host_city
            ),
            "country": clean_nullable_string(
                host_country
            ),
            "country_code": classification.get(
                "host_country_code"
            ),
            "format": slugify(
                str(opportunity_format)
            ),
        },

        "dates": {
            "application_deadline": clean_date(
                application_deadline
            ),
            "start_date": clean_date(
                start_date
            ),
            "end_date": clean_date(
                end_date
            ),
        },

        "eligibility": {
            "geographic_regions": (
                classification.get(
                    "geographic_region_slugs",
                    [],
                )
            ),
            "eligible_countries": (
                eligible_countries
            ),
            "academic_levels": (
                classification.get(
                    "academic_level_slugs",
                    [],
                )
            ),
            "audience_access": audience_access,
            "audience_groups": (
                classification.get(
                    "audience_group_slugs",
                    [],
                )
            ),
        },

        "academic_fields": {
            "broad_fields": (
                classification.get(
                    "broad_field_slugs",
                    [],
                )
            ),
            "majors": classification.get(
                "major_slugs",
                [],
            ),
        },

        "funding": {
            "types": classification.get(
                "funding_slugs",
                [],
            ),
            "fee": participation_fee,
        },

        "career_themes": (
            classification.get(
                "career_theme_slugs",
                [],
            )
        ),

        "tags": classification.get(
            "keyword_slugs",
            [],
        ),

        "verification": {
            "source_type": (
                "contributor-supplied-official-source"
            ),
            "reviewed": False,
            "reviewed_by": None,
            "reviewed_at": None,
            "ai_confidence": moderation.get(
                "confidence"
            ),
            "ai_recommended_action": (
                moderation.get(
                    "recommended_action"
                )
            ),
        },

        "submission": {
            "issue_number": int(
                ISSUE_NUMBER
            ),
            "submitted_by": first_value(
                submission,
                [
                    "submitted_by",
                    "author",
                    "github_username",
                ],
                None,
            ),
            "ai_formatted": True,
        },
    }


def build_markdown_body(
    submission: dict[str, Any],
    ai_result: dict[str, Any],
) -> str:
    display = ai_result.get(
        "display",
        {},
    )

    moderation = ai_result.get(
        "moderation",
        {},
    )

    title = (
        display.get("official_name")
        or first_value(
            submission,
            [
                "opportunity_name",
                "Opportunity name",
                "title",
            ],
            "Untitled Opportunity",
        )
    )

    emoji = (
        display.get("suggested_emoji")
        or "🗺️"
    )

    summary = (
        display.get("short_summary")
        or first_value(
            submission,
            [
                "short_description",
                "What is this quest?",
            ],
            "No description was supplied.",
        )
    )

    organizer = first_value(
        submission,
        [
            "organizer",
            "Organizer",
        ],
        "Not confirmed",
    )

    official_url = first_value(
        submission,
        [
            "official_website",
            "Official opportunity page",
            "official_link",
        ],
        "",
    )

    application_url = first_value(
        submission,
        [
            "application_link",
            "Direct application portal",
        ],
        "",
    )

    activities = first_value(
        submission,
        [
            "activities",
            "Main activities",
        ],
        "",
    )

    benefits = first_value(
        submission,
        [
            "benefits",
            "Quest rewards",
        ],
        "",
    )

    funding_details = first_value(
        submission,
        [
            "funding_details",
            "Funding details",
        ],
        "",
    )

    eligibility_details = first_value(
        submission,
        [
            "nationality_residency_rules",
            "Nationality or residency requirements",
            "eligibility_details",
        ],
        "",
    )

    source_notes = first_value(
        submission,
        [
            "source_notes",
            "Verification notes",
        ],
        "",
    )

    missing = moderation.get(
        "missing_required_information",
        [],
    )

    ambiguous = moderation.get(
        "ambiguous_information",
        [],
    )

    contradictions = moderation.get(
        "contradictions",
        [],
    )

    sections = [
        f"# {emoji} {title}",
        "",
        "## 📖 The Quest",
        "",
        str(summary).strip(),
        "",
        "## 🏰 Organizer",
        "",
        str(organizer).strip(),
    ]

    if eligibility_details:
        sections.extend(
            [
                "",
                "## 🧭 Who May Enter",
                "",
                str(
                    eligibility_details
                ).strip(),
            ]
        )

    if activities:
        sections.extend(
            [
                "",
                "## ⚒️ What Adventurers Will Do",
                "",
                str(activities).strip(),
            ]
        )

    if benefits or funding_details:
        sections.extend(
            [
                "",
                "## 🎒 Provisions and Rewards",
                "",
            ]
        )

        if benefits:
            sections.append(
                str(benefits).strip()
            )

        if funding_details:
            sections.extend(
                [
                    "",
                    str(
                        funding_details
                    ).strip(),
                ]
            )

    sections.extend(
        [
            "",
            "## 🔗 Official Portals",
            "",
        ]
    )

    if official_url:
        sections.append(
            f"- [Official opportunity page]({official_url})"
        )

    if application_url:
        sections.append(
            f"- [Application portal]({application_url})"
        )

    if (
        not official_url
        and not application_url
    ):
        sections.append(
            "- Not confirmed"
        )

    sections.extend(
        [
            "",
            "## 🔍 Moderator Notes",
            "",
            (
                "- **Missing information:** "
                + (
                    ", ".join(missing)
                    if missing
                    else "None flagged"
                )
            ),
            (
                "- **Ambiguous information:** "
                + (
                    ", ".join(ambiguous)
                    if ambiguous
                    else "None flagged"
                )
            ),
            (
                "- **Possible contradictions:** "
                + (
                    ", ".join(contradictions)
                    if contradictions
                    else "None flagged"
                )
            ),
        ]
    )

    if source_notes:
        sections.extend(
            [
                "",
                "### 📚 Contributor Verification Notes",
                "",
                str(source_notes).strip(),
            ]
        )

    sections.extend(
        [
            "",
            "---",
            "",
            (
                "> 🤖 This page was generated from "
                "contributor-supplied information and "
                "AI-assisted formatting. It remains "
                "unverified until approved by a human "
                "moderator."
            ),
        ]
    )

    return (
        "\n".join(sections).strip()
        + "\n"
    )


def write_github_output(
    name: str,
    value: str,
) -> None:
    output_path = os.environ.get(
        "GITHUB_OUTPUT"
    )

    if not output_path:
        print(f"{name}={value}")
        return

    with open(
        output_path,
        "a",
        encoding="utf-8",
    ) as output:
        output.write(
            f"{name}={value}\n"
        )


def main() -> None:
    submission = read_json(
        SUBMISSION_FILE
    )

    ai_result = read_json(
        AI_OUTPUT_FILE
    )

    front_matter = build_front_matter(
        submission,
        ai_result,
    )

    body = build_markdown_body(
        submission,
        ai_result,
    )

    category = front_matter[
        "category"
    ]

    slug = front_matter[
        "slug"
    ]

    destination_directory = (
        OPPORTUNITIES_DIRECTORY
        / category
    )

    destination_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination_file = (
        destination_directory
        / f"{slug}.md"
    )

    if destination_file.exists():
        destination_file = (
            destination_directory
            / f"{slug}-{ISSUE_NUMBER}.md"
        )

    complete_document = (
        yaml_front_matter(
            front_matter
        )
        + "\n\n"
        + body
    )

    destination_file.write_text(
        complete_document,
        encoding="utf-8",
    )

    write_github_output(
        "opportunity_file",
        str(destination_file),
    )

    write_github_output(
        "opportunity_category",
        category,
    )

    write_github_output(
        "opportunity_slug",
        slug,
    )

    print(
        "Generated opportunity page: "
        f"{destination_file}"
    )


if __name__ == "__main__":
    main()
