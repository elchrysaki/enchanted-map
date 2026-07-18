from __future__ import annotations

import html
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

from opportunity_document import (
    OpportunityDocumentError,
    parse_opportunity_document,
    render_opportunity_document,
)


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
MAX_URL_LENGTH = 2_000

ALLOWED_SCHEMES = {"http", "https"}

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

ALLOWED_SPECIFIC_CATEGORIES = {
    "conference",
    "summit",
    "forum",
    "workshop-seminar",
    "networking-event",
    "congress",
    "cultural-program",
    "internship",
    "apprenticeship",
    "traineeship",
    "competition",
    "challenge",
    "hackathon",
    "research-program",
    "research-placement",
    "research-internship",
    "fellowship",
    "leadership-program",
    "scholarship",
    "grant",
    "travel-grant",
    "academy",
    "summer-school",
    "winter-school",
    "course-training",
    "bootcamp",
    "startup-program",
    "accelerator",
    "incubator",
    "entrepreneurship-program",
    "creative-call",
    "media-call",
    "writing-call",
    "design-call",
    "exchange-program",
    "mobility-program",
    "volunteering-program",
    "service-program",
    "other",
}

SPECIFIC_CATEGORIES_BY_MAIN = {
    "events": {
        "conference",
        "summit",
        "forum",
        "workshop-seminar",
        "networking-event",
        "congress",
        "cultural-program",
    },
    "internships": {
        "internship",
        "apprenticeship",
        "traineeship",
    },
    "competitions": {
        "competition",
        "challenge",
        "hackathon",
    },
    "research": {
        "research-program",
        "research-placement",
        "research-internship",
    },
    "fellowships": {
        "fellowship",
        "leadership-program",
    },
    "scholarships": {
        "scholarship",
        "grant",
        "travel-grant",
    },
    "courses": {
        "academy",
        "summer-school",
        "winter-school",
        "course-training",
        "bootcamp",
    },
    "innovation": {
        "startup-program",
        "accelerator",
        "incubator",
        "entrepreneurship-program",
    },
    "creative-calls": {
        "creative-call",
        "media-call",
        "writing-call",
        "design-call",
    },
    "exchanges": {
        "exchange-program",
        "mobility-program",
    },
    "volunteering": {
        "volunteering-program",
        "service-program",
    },
    "other": {
        "other",
    },
}

ALLOWED_FORMATS = {
    "in-person",
    "online",
    "hybrid",
    "travelling",
    "multiple-formats",
    "not-confirmed",
}

ALLOWED_AUDIENCE_ACCESS_MODELS = {
    "eligible",
    "encouraged",
    "priority",
    "exclusive",
    "focus-unclear",
    "not-confirmed",
}

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


def require_object(
    parent: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    value = parent.get(key)

    if not isinstance(value, dict):
        fail(f"'{key}' must be a JSON object.")

    return value


def require_list(
    parent: dict[str, Any],
    key: str,
) -> list[Any]:
    value = parent.get(key)

    if not isinstance(value, list):
        fail(f"'{key}' must be a JSON list.")

    return value


def clean_text(
    value: Any,
    field_name: str,
    *,
    maximum: int = MAX_SECTION_LENGTH,
    required: bool = False,
) -> str | None:
    if value is None:
        if required:
            fail(f"'{field_name}' must contain text.")
        return None

    if not isinstance(value, str):
        fail(f"'{field_name}' must be a string or null.")

    cleaned = value.strip()

    if not cleaned:
        if required:
            fail(f"'{field_name}' must contain text.")
        return None

    if len(cleaned) > maximum:
        fail(
            f"'{field_name}' exceeds the maximum length "
            f"of {maximum} characters."
        )

    return cleaned


def clean_string_list(
    value: Any,
    field_name: str,
    *,
    maximum: int = MAX_LIST_ITEMS,
) -> list[str]:
    if not isinstance(value, list):
        fail(f"'{field_name}' must be a JSON list.")

    if len(value) > maximum:
        fail(
            f"'{field_name}' contains too many values. "
            f"Maximum: {maximum}."
        )

    result: list[str] = []

    for index, item in enumerate(value):
        cleaned = clean_text(
            item,
            f"{field_name}[{index}]",
            required=True,
        )

        if cleaned is None:
            fail(f"'{field_name}[{index}]' must contain text.")

        result.append(cleaned)

    return result


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


def validate_web_url(
    value: Any,
    field_name: str,
) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        fail(f"'{field_name}' must be a string or null.")

    candidate = value.strip()

    if not candidate:
        fail(f"'{field_name}' must not be an empty string.")

    if len(candidate) > MAX_URL_LENGTH:
        fail(f"'{field_name}' exceeds the URL length limit.")

    if any(
        character in candidate
        for character in ("\r", "\n", "\t", " ", "<", ">", '"')
    ):
        fail(f"'{field_name}' contains unsafe URL characters.")

    try:
        parsed = urlparse(candidate)
        port = parsed.port
    except ValueError as exc:
        fail(f"'{field_name}' is not a valid URL: {exc}")

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        fail(f"'{field_name}' must use HTTP or HTTPS.")

    if not parsed.hostname:
        fail(f"'{field_name}' must include a hostname.")

    if parsed.username or parsed.password:
        fail(f"'{field_name}' must not contain credentials.")

    if port not in (None, 80, 443):
        fail(f"'{field_name}' must not use a non-standard port.")

    return candidate


def yaml_safe_dump(data: dict[str, Any]) -> str:
    return yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=1000,
    ).strip()


# ============================================================
# SCHEMA VALIDATION
# ============================================================

def validate_issue_number(
    record: dict[str, Any],
    record_name: str,
) -> None:
    issue_number = record.get("issue_number")

    if (
        not isinstance(issue_number, int)
        or isinstance(issue_number, bool)
        or issue_number != ISSUE_NUMBER
    ):
        fail(
            f"{record_name} issue number must match "
            "the workflow ISSUE_NUMBER."
        )


def validate_category_pair(
    main_category: str,
    category: str,
) -> None:
    if main_category not in ALLOWED_MAIN_CATEGORIES:
        fail(
            f"Invalid main category: {main_category}"
        )

    if category not in ALLOWED_SPECIFIC_CATEGORIES:
        fail(
            f"Invalid specific category: {category}"
        )

    if category == "other":
        return

    expected_categories = SPECIFIC_CATEGORIES_BY_MAIN.get(
        main_category,
        set(),
    )

    if category not in expected_categories:
        fail(
            "Category mismatch: "
            f"'{category}' does not belong under "
            f"'{main_category}'. The generator will not "
            "silently remap it."
        )


def researched_audience_groups(
    researched: dict[str, Any],
) -> list[str]:
    audience = require_object(researched, "audience")

    if (
        audience.get("classification_source")
        != "submitted-dropdown-only"
    ):
        fail(
            "Researched audience classification_source must be "
            "'submitted-dropdown-only'."
        )

    return clean_string_list(
        require_list(audience, "groups"),
        "researched.audience.groups",
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
            "Research input is not a researched-submission record."
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
        "Research input",
    )
    validate_issue_number(
        publishable,
        "Publishable input",
    )

    identity = require_object(
        publishable,
        "identity",
    )

    title = clean_text(
        identity.get("title"),
        "identity.title",
        maximum=MAX_TITLE_LENGTH,
        required=True,
    )

    if title is None:
        fail("'identity.title' must contain text.")

    main_category = clean_text(
        identity.get("main_category"),
        "identity.main_category",
        maximum=100,
        required=True,
    )
    category = clean_text(
        identity.get("category"),
        "identity.category",
        maximum=100,
        required=True,
    )

    if main_category is None or category is None:
        fail(
            "Both identity categories must contain text."
        )

    validate_category_pair(
        main_category,
        category,
    )

    location = require_object(
        publishable,
        "location",
    )
    opportunity_format = location.get("format")

    if opportunity_format not in ALLOWED_FORMATS:
        fail(
            f"Invalid normalized format: {opportunity_format}"
        )

    audience = require_object(
        publishable,
        "audience",
    )

    if (
        audience.get("classification_source")
        != "submitted-dropdown-only"
    ):
        fail(
            "Publishable audience classification_source must be "
            "'submitted-dropdown-only'."
        )

    access_model = audience.get("access_model")

    if access_model not in ALLOWED_AUDIENCE_ACCESS_MODELS:
        fail(
            f"Invalid audience access model: {access_model}"
        )

    researched_groups = researched_audience_groups(
        researched
    )
    publishable_groups = clean_string_list(
        require_list(audience, "groups"),
        "publishable.audience.groups",
    )

    if publishable_groups != researched_groups:
        fail(
            "Publishable audience groups must exactly match "
            "the researched submitted-dropdown groups, "
            "including order."
        )

    filters = require_object(
        publishable,
        "filters",
    )

    main_category_filters = clean_string_list(
        require_list(filters, "main_categories"),
        "filters.main_categories",
    )
    category_filters = clean_string_list(
        require_list(filters, "categories"),
        "filters.categories",
    )
    audience_filters = clean_string_list(
        require_list(filters, "audience_groups"),
        "filters.audience_groups",
    )

    if main_category_filters != [main_category]:
        fail(
            "filters.main_categories must exactly equal "
            "[identity.main_category]."
        )

    if category_filters != [category]:
        fail(
            "filters.categories must exactly equal "
            "[identity.category]."
        )

    if audience_filters != publishable_groups:
        fail(
            "filters.audience_groups must exactly match "
            "audience.groups, including order."
        )

    application = require_object(
        publishable,
        "application",
    )

    validate_web_url(
        application.get("official_page"),
        "application.official_page",
    )
    validate_web_url(
        application.get("application_page"),
        "application.application_page",
    )

    require_object(
        publishable,
        "dates",
    )
    require_object(
        publishable,
        "eligibility",
    )
    require_object(
        publishable,
        "funding",
    )
    require_object(
        publishable,
        "program",
    )
    require_object(
        publishable,
        "page_content",
    )
    require_object(
        publishable,
        "publication_notes",
    )

    moderation = require_object(
        publishable,
        "moderation",
    )

    if moderation.get("human_review_required") is not True:
        fail(
            "Publishable draft must require human review."
        )

    if (
        moderation.get("safe_to_generate_draft_page")
        is not True
    ):
        fail(
            "The formatter did not mark this record safe "
            "to generate as a draft page."
        )

    action = moderation.get("recommended_action")

    if action not in ALLOWED_ACTIONS:
        fail(
            f"Invalid formatter recommended action: {action}"
        )

    if action != "continue-to-draft-pr":
        fail(
            "The formatter must recommend "
            "'continue-to-draft-pr' before generation."
        )


# ============================================================
# STRUCTURED DATA EXTRACTION
# ============================================================

def normalized_date(
    dates: dict[str, Any],
    key: str,
) -> dict[str, str | None]:
    value = require_object(dates, key)

    display = clean_text(
        value.get("display"),
        f"dates.{key}.display",
    )
    normalized = clean_text(
        value.get("normalized"),
        f"dates.{key}.normalized",
        maximum=10,
    )

    if normalized is not None:
        try:
            parsed = datetime.strptime(
                normalized,
                "%Y-%m-%d",
            ).date()
        except ValueError:
            fail(
                f"'dates.{key}.normalized' must use "
                "a real YYYY-MM-DD date."
            )

        if parsed.isoformat() != normalized:
            fail(
                f"'dates.{key}.normalized' must be "
                "zero-padded YYYY-MM-DD."
            )

    return {
        "display": display,
        "normalized": normalized,
    }


def clean_additional_dates(
    value: Any,
) -> list[str | dict[str, str | None]]:
    if not isinstance(value, list):
        fail("'dates.additional_dates' must be a JSON list.")

    if len(value) > 50:
        fail(
            "'dates.additional_dates' contains too many values."
        )

    result: list[str | dict[str, str | None]] = []

    for index, item in enumerate(value):
        field_name = f"dates.additional_dates[{index}]"

        if isinstance(item, str):
            cleaned = clean_text(
                item,
                field_name,
                required=True,
            )

            if cleaned is None:
                fail(f"'{field_name}' must contain text.")

            result.append(cleaned)
            continue

        if isinstance(item, dict):
            display = clean_text(
                item.get("display"),
                f"{field_name}.display",
            )
            normalized = clean_text(
                item.get("normalized"),
                f"{field_name}.normalized",
                maximum=10,
            )

            if normalized is not None:
                try:
                    parsed = datetime.strptime(
                        normalized,
                        "%Y-%m-%d",
                    ).date()
                except ValueError:
                    fail(
                        f"'{field_name}.normalized' must use "
                        "a real YYYY-MM-DD date."
                    )

                if parsed.isoformat() != normalized:
                    fail(
                        f"'{field_name}.normalized' must be "
                        "zero-padded YYYY-MM-DD."
                    )

            result.append(
                {
                    "display": display,
                    "normalized": normalized,
                }
            )
            continue

        fail(
            f"'{field_name}' must be a string "
            "or a date object."
        )

    return result


def raw_researched_value(
    researched: dict[str, Any],
    section_name: str,
    field_name: str,
) -> str | None:
    section = researched.get(section_name)

    if not isinstance(section, dict):
        return None

    field = section.get(field_name)

    if not isinstance(field, dict):
        return None

    return clean_text(
        field.get("raw"),
        f"researched.{section_name}.{field_name}.raw",
    )


def verified_confidence(
    researched: dict[str, Any],
) -> int:
    research_summary = researched.get(
        "research_summary",
        {},
    )

    if not isinstance(research_summary, dict):
        return 0

    value = research_summary.get(
        "overall_confidence",
        0,
    )

    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
        or value > 100
    ):
        return 0

    return value


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

    main_category = clean_text(
        identity.get("main_category"),
        "identity.main_category",
        maximum=100,
        required=True,
    )
    category = clean_text(
        identity.get("category"),
        "identity.category",
        maximum=100,
        required=True,
    )

    if main_category is None or category is None:
        fail(
            "Both identity categories must contain text."
        )

    opportunity_format = clean_text(
        location.get("format"),
        "location.format",
        maximum=100,
        required=True,
    )

    if opportunity_format is None:
        fail("'location.format' must contain text.")

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

    return {
        "schema_version": 2,
        "record_type": "opportunity",
        "slug": slug,
        "title": clean_text(
            identity.get("title"),
            "identity.title",
            maximum=MAX_TITLE_LENGTH,
            required=True,
        ),
        "organizer": clean_text(
            identity.get("organizer"),
            "identity.organizer",
            maximum=MAX_TITLE_LENGTH,
        ),
        "main_category": main_category,
        "category": category,
        "edition": clean_text(
            identity.get("edition"),
            "identity.edition",
            maximum=100,
        ),
        "status": "pending-review",
        "summary": clean_text(
            publishable.get("summary"),
            "summary",
        ),
        "format": opportunity_format,
        "location": {
            "display": clean_text(
                location.get("display"),
                "location.display",
            ),
            "host_city": clean_text(
                location.get("host_city"),
                "location.host_city",
                maximum=200,
            ),
            "host_country": clean_text(
                location.get("host_country"),
                "location.host_country",
                maximum=200,
            ),
            "host_country_code": clean_text(
                location.get("host_country_code"),
                "location.host_country_code",
                maximum=2,
            ),
            "additional_locations": clean_string_list(
                require_list(
                    location,
                    "additional_locations",
                ),
                "location.additional_locations",
                maximum=50,
            ),
        },
        "dates": {
            "application_deadline": {
                "raw": raw_researched_value(
                    researched,
                    "dates",
                    "application_deadline",
                ),
                "display": application_deadline["display"],
                "normalized": application_deadline["normalized"],
            },
            "start_date": start_date,
            "end_date": end_date,
            "additional_dates": clean_additional_dates(
                require_list(
                    dates,
                    "additional_dates",
                )
            ),
        },
        "eligibility": {
            "geographic_regions": clean_string_list(
                require_list(
                    eligibility,
                    "geographic_regions",
                ),
                "eligibility.geographic_regions",
            ),
            "eligible_countries": clean_string_list(
                require_list(
                    eligibility,
                    "eligible_countries",
                ),
                "eligibility.eligible_countries",
            ),
            "nationality_or_residency_rules": clean_text(
                eligibility.get(
                    "nationality_or_residency_rules"
                ),
                "eligibility.nationality_or_residency_rules",
            ),
            "academic_levels": clean_string_list(
                require_list(
                    eligibility,
                    "academic_levels",
                ),
                "eligibility.academic_levels",
            ),
            "broad_fields": clean_string_list(
                require_list(
                    eligibility,
                    "broad_fields",
                ),
                "eligibility.broad_fields",
            ),
            "specific_majors": clean_string_list(
                require_list(
                    eligibility,
                    "specific_majors",
                ),
                "eligibility.specific_majors",
            ),
            "age_requirements": clean_text(
                eligibility.get("age_requirements"),
                "eligibility.age_requirements",
            ),
            "experience_requirements": clean_text(
                eligibility.get(
                    "experience_requirements"
                ),
                "eligibility.experience_requirements",
            ),
            "language_requirements": clean_text(
                eligibility.get(
                    "language_requirements"
                ),
                "eligibility.language_requirements",
            ),
            "display_points": clean_string_list(
                require_list(
                    eligibility,
                    "display_points",
                ),
                "eligibility.display_points",
            ),
        },
        "audience": {
            "classification_source": (
                "submitted-dropdown-only"
            ),
            "groups": clean_string_list(
                require_list(audience, "groups"),
                "audience.groups",
            ),
            "access_model": clean_text(
                audience.get("access_model"),
                "audience.access_model",
                maximum=100,
                required=True,
            ),
            "display_points": clean_string_list(
                require_list(
                    audience,
                    "display_points",
                ),
                "audience.display_points",
            ),
        },
        "funding": {
            "application_fee": clean_text(
                funding.get("application_fee"),
                "funding.application_fee",
            ),
            "participation_fee": clean_text(
                funding.get("participation_fee"),
                "funding.participation_fee",
            ),
            "scholarship": clean_text(
                funding.get("scholarship"),
                "funding.scholarship",
            ),
            "travel_support": clean_text(
                funding.get("travel_support"),
                "funding.travel_support",
            ),
            "accommodation": clean_text(
                funding.get("accommodation"),
                "funding.accommodation",
            ),
            "meals": clean_text(
                funding.get("meals"),
                "funding.meals",
            ),
            "stipend_or_salary": clean_text(
                funding.get("stipend_or_salary"),
                "funding.stipend_or_salary",
            ),
            "prizes": clean_text(
                funding.get("prizes"),
                "funding.prizes",
            ),
            "visa_support": clean_text(
                funding.get("visa_support"),
                "funding.visa_support",
            ),
            "accessibility_support": clean_text(
                funding.get(
                    "accessibility_support"
                ),
                "funding.accessibility_support",
            ),
            "other_support": clean_string_list(
                require_list(
                    funding,
                    "other_support",
                ),
                "funding.other_support",
            ),
            "display_points": clean_string_list(
                require_list(
                    funding,
                    "display_points",
                ),
                "funding.display_points",
            ),
        },
        "application": {
            "official_page": validate_web_url(
                application.get("official_page"),
                "application.official_page",
            ),
            "application_page": validate_web_url(
                application.get("application_page"),
                "application.application_page",
            ),
            "requirements": clean_string_list(
                require_list(
                    application,
                    "requirements",
                ),
                "application.requirements",
            ),
            "documents": clean_string_list(
                require_list(
                    application,
                    "documents",
                ),
                "application.documents",
            ),
            "selection_process": clean_string_list(
                require_list(
                    application,
                    "selection_process",
                ),
                "application.selection_process",
            ),
            "display_points": clean_string_list(
                require_list(
                    application,
                    "display_points",
                ),
                "application.display_points",
            ),
        },
        "program": {
            "activities": clean_string_list(
                require_list(
                    program,
                    "activities",
                ),
                "program.activities",
            ),
            "benefits": clean_string_list(
                require_list(
                    program,
                    "benefits",
                ),
                "program.benefits",
            ),
            "topics": clean_string_list(
                require_list(
                    program,
                    "topics",
                ),
                "program.topics",
            ),
        },
        "filters": {
            key: clean_string_list(
                require_list(filters, key),
                f"filters.{key}",
            )
            for key in (
                "main_categories",
                "categories",
                "formats",
                "host_countries",
                "eligible_regions",
                "eligible_countries",
                "academic_levels",
                "academic_fields",
                "subjects",
                "audience_groups",
                "funding_features",
                "topics",
            )
        },
        "tags": clean_string_list(
            require_list(publishable, "tags"),
            "tags",
            maximum=MAX_TAGS,
        ),
        "verification": {
            "human_review_required": True,
            "safe_to_generate_draft_page": True,
            "research_confidence": verified_confidence(
                researched
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
            "identity_categories_locked_to_research": (
                publication_provenance.get(
                    "identity_categories_locked_to_research",
                    True,
                )
            ),
            "audience_groups_locked_to_research": True,
            "automatically_verified": False,
            "automatically_published": False,
        },
        "submission": {
            "issue_number": ISSUE_NUMBER,
            "issue_url": validate_web_url(
                research_provenance.get(
                    "original_issue_url"
                ),
                "provenance.original_issue_url",
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


def synchronize_filter_mirrors(
    record: dict[str, Any],
) -> None:
    """Copy structured source fields into mirrored filters exactly."""

    location = require_object(record, "location")
    eligibility = require_object(record, "eligibility")
    audience = require_object(record, "audience")
    program = require_object(record, "program")
    filters = require_object(record, "filters")

    main_category = clean_text(
        record.get("main_category"),
        "main_category",
        maximum=100,
        required=True,
    )
    category = clean_text(
        record.get("category"),
        "category",
        maximum=100,
        required=True,
    )
    opportunity_format = clean_text(
        record.get("format"),
        "format",
        maximum=100,
        required=True,
    )
    host_country = clean_text(
        location.get("host_country"),
        "location.host_country",
        maximum=200,
    )

    if main_category is None or category is None or opportunity_format is None:
        fail("Cannot synchronize filters without identity fields.")

    filters["main_categories"] = [main_category]
    filters["categories"] = [category]
    filters["formats"] = [opportunity_format]
    filters["host_countries"] = [host_country] if host_country else []
    filters["eligible_regions"] = list(
        eligibility.get("geographic_regions") or []
    )
    filters["eligible_countries"] = list(
        eligibility.get("eligible_countries") or []
    )
    filters["academic_levels"] = list(
        eligibility.get("academic_levels") or []
    )
    filters["academic_fields"] = list(
        eligibility.get("broad_fields") or []
    )
    filters["subjects"] = list(
        eligibility.get("specific_majors") or []
    )
    filters["audience_groups"] = list(
        audience.get("groups") or []
    )
    filters["topics"] = list(program.get("topics") or [])


# ============================================================
# MARKDOWN GENERATION
# ============================================================

def markdown_plain_text(value: str) -> str:
    escaped = html.escape(value, quote=False)
    escaped = escaped.replace("\\", "\\\\")
    escaped = escaped.replace("`", "\\`")
    escaped = escaped.replace("*", "\\*")
    escaped = escaped.replace("_", "\\_")
    escaped = escaped.replace("[", "\\[")
    escaped = escaped.replace("]", "\\]")

    safe_lines: list[str] = []
    for line in escaped.splitlines():
        if re.match(
            r"^\s*(?:#{1,6}|>|[-+]\s|\d+[.)]\s)",
            line,
        ):
            line = "\\" + line
        safe_lines.append(line)

    return "\n".join(safe_lines)


def markdown_inline(value: str) -> str:
    return markdown_plain_text(" ".join(value.split()))


def markdown_link(label: str, url: str) -> str:
    return f"[{markdown_inline(label)}]({url})"


def display_value(value: Any, fallback: str = "Not confirmed") -> str:
    if isinstance(value, str) and value.strip():
        return markdown_inline(value.strip())
    return fallback


def category_label(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "Opportunity"
    return value.replace("-", " ").title()


def add_text_section(
    lines: list[str],
    heading: str,
    text: Any,
    field_name: str,
) -> None:
    cleaned = clean_text(text, field_name)
    if not cleaned:
        return
    lines.extend(
        [
            f"## {heading}",
            "",
            markdown_plain_text(cleaned),
            "",
        ]
    )


def add_official_links(
    lines: list[str],
    official_page: str | None,
    application_page: str | None,
) -> None:
    links: list[str] = []
    if official_page:
        links.append(
            markdown_link("🌐 Explore the official page", official_page)
        )
    if application_page:
        links.append(
            markdown_link("🚀 Start your application", application_page)
        )
    if not links:
        return

    lines.extend(["## 🔗 Official links", ""])
    for link in links:
        lines.append(f"- **{link}**")
    lines.append("")


def build_markdown_body(
    front_matter: dict[str, Any],
    publishable: dict[str, Any],
) -> str:
    identity = require_object(publishable, "identity")
    page_content = require_object(publishable, "page_content")
    application = require_object(publishable, "application")

    title = clean_text(
        identity.get("title"),
        "identity.title",
        maximum=MAX_TITLE_LENGTH,
        required=True,
    )
    if title is None:
        fail("'identity.title' must contain text.")

    summary = clean_text(publishable.get("summary"), "summary")
    organizer = display_value(front_matter.get("organizer"), "Organizer not confirmed")
    category = category_label(front_matter.get("category"))
    opportunity_format = category_label(front_matter.get("format"))

    location = front_matter.get("location")
    location_display = (
        display_value(location.get("display"))
        if isinstance(location, dict)
        else "Not confirmed"
    )

    dates = front_matter.get("dates")
    deadline = "Not confirmed"
    program_dates = "Not confirmed"
    if isinstance(dates, dict):
        deadline_field = dates.get("application_deadline")
        if isinstance(deadline_field, dict):
            deadline = display_value(deadline_field.get("display"))

        start_field = dates.get("start_date")
        end_field = dates.get("end_date")
        start_display = (
            display_value(start_field.get("display"), "")
            if isinstance(start_field, dict)
            else ""
        )
        end_display = (
            display_value(end_field.get("display"), "")
            if isinstance(end_field, dict)
            else ""
        )
        if start_display and end_display:
            program_dates = f"{start_display} to {end_display}"
        elif start_display or end_display:
            program_dates = start_display or end_display

    official_page = validate_web_url(
        application.get("official_page"),
        "application.official_page",
    )
    application_page = validate_web_url(
        application.get("application_page"),
        "application.application_page",
    )

    lines: list[str] = [
        f"# 🧭 {markdown_inline(title)}",
        "",
        f"**{organizer}**",
        "",
        f"🎯 **{markdown_inline(category)}** · "
        f"💻 **{markdown_inline(opportunity_format)}** · "
        f"📍 **{location_display}**",
        "",
    ]

    top_links: list[str] = []
    if official_page:
        top_links.append(markdown_link("🌐 Official page", official_page))
    if application_page:
        top_links.append(markdown_link("🚀 Apply now", application_page))
    if top_links:
        lines.extend([" · ".join(f"**{link}**" for link in top_links), ""])

    if summary:
        lines.extend(["> [!TIP]"])
        summary_lines = markdown_plain_text(summary).splitlines() or [""]
        lines.extend(f"> {line}" for line in summary_lines)
        lines.append("")

    lines.extend(
        [
            "> [!IMPORTANT]",
            f"> **Application deadline:** {deadline}  ",
            f"> **Program dates:** {program_dates}  ",
            f"> **Location:** {location_display}  ",
            f"> **Format:** {markdown_inline(opportunity_format)}",
            "",
            "---",
            "",
        ]
    )

    add_text_section(
        lines,
        "✨ Why this opportunity is worth your attention",
        page_content.get("overview"),
        "page_content.overview",
    )
    add_text_section(
        lines,
        "🏛️ Meet the organizer",
        page_content.get("organizer"),
        "page_content.organizer",
    )
    add_text_section(
        lines,
        "👥 Who can apply",
        page_content.get("who_can_apply"),
        "page_content.who_can_apply",
    )
    add_text_section(
        lines,
        "📍 Where and how it happens",
        page_content.get("location_and_format"),
        "page_content.location_and_format",
    )
    add_text_section(
        lines,
        "🗓️ Dates to remember",
        page_content.get("important_dates"),
        "page_content.important_dates",
    )
    add_text_section(
        lines,
        "💸 Fees, funding and support",
        page_content.get("funding_and_support"),
        "page_content.funding_and_support",
    )
    add_text_section(
        lines,
        "🛠️ What you will do",
        page_content.get("what_participants_do"),
        "page_content.what_participants_do",
    )
    add_text_section(
        lines,
        "🚀 How to apply",
        page_content.get("application_path"),
        "page_content.application_path",
    )

    add_official_links(lines, official_page, application_page)

    submission = front_matter.get("submission", {})
    issue_url = submission.get("issue_url") if isinstance(submission, dict) else None
    if isinstance(issue_url, str) and issue_url.strip():
        lines.extend(
            [
                "---",
                "",
                "<details>",
                "<summary><strong>🧾 Research and review trail</strong></summary>",
                "",
                "This page was prepared from a community submission, "
                "checked against official sources, and routed through "
                "human moderator review before publication.",
                "",
                "- " + markdown_link("View the original submission", issue_url),
                "",
                "</details>",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


# ============================================================
# FILE CREATION
# ============================================================

def existing_issue_number(
    path: Path,
) -> int | None:
    if not path.exists():
        return None

    try:
        content = path.read_text(encoding="utf-8")
        metadata, _body = parse_opportunity_document(content)
    except (OSError, OpportunityDocumentError):
        return None

    submission = metadata.get("submission")
    if not isinstance(submission, dict):
        return None

    issue_number = submission.get("issue_number")
    if isinstance(issue_number, int) and not isinstance(issue_number, bool):
        return issue_number

    return None


def choose_output_path(
    main_category: str,
    base_slug: str,
) -> tuple[Path, str]:
    category_directory = (
        OPPORTUNITIES_DIRECTORY
        / main_category
    )

    category_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    base_path = category_directory / f"{base_slug}.md"

    if (
        not base_path.exists()
        or existing_issue_number(base_path)
        == ISSUE_NUMBER
    ):
        return base_path, base_slug

    issue_slug = f"{base_slug}-{ISSUE_NUMBER}"
    issue_path = (
        category_directory
        / f"{issue_slug}.md"
    )

    if (
        not issue_path.exists()
        or existing_issue_number(issue_path)
        == ISSUE_NUMBER
    ):
        return issue_path, issue_slug

    fail(
        "Both the normal opportunity path and the "
        "issue-qualified path already belong to different "
        "submissions. Refusing to overwrite either file."
    )


def write_text_atomically(
    path: Path,
    content: str,
) -> None:
    temporary_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary_path.write_text(
        content,
        encoding="utf-8",
    )

    temporary_path.replace(path)


def create_opportunity_file(
    researched: dict[str, Any],
    publishable: dict[str, Any],
) -> tuple[Path, str, str, str]:
    identity = require_object(
        publishable,
        "identity",
    )

    title = clean_text(
        identity.get("title"),
        "identity.title",
        maximum=MAX_TITLE_LENGTH,
        required=True,
    )

    if title is None:
        fail(
            "Cannot generate an opportunity page without a title."
        )

    main_category = clean_text(
        identity.get("main_category"),
        "identity.main_category",
        maximum=100,
        required=True,
    )
    category = clean_text(
        identity.get("category"),
        "identity.category",
        maximum=100,
        required=True,
    )

    if main_category is None or category is None:
        fail(
            "Cannot generate an opportunity page without "
            "both categories."
        )

    validate_category_pair(
        main_category,
        category,
    )

    base_slug = slugify(title)

    if not base_slug:
        base_slug = f"opportunity-{ISSUE_NUMBER}"

    output_file, slug = choose_output_path(
        main_category,
        base_slug,
    )

    front_matter = build_front_matter(
        researched,
        publishable,
        slug,
    )

    synchronize_filter_mirrors(front_matter)

    body = build_markdown_body(
        front_matter,
        publishable,
    )

    content = render_opportunity_document(
        front_matter,
        body,
    )

    write_text_atomically(
        output_file,
        content,
    )

    return (
        output_file,
        main_category,
        category,
        slug,
    )


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

    (
        output_file,
        main_category,
        category,
        slug,
    ) = create_opportunity_file(
        researched,
        publishable,
    )

    write_github_output(
        "opportunity_file",
        str(output_file),
    )
    write_github_output(
        "main_category",
        main_category,
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
        "OffMap opportunity Markdown draft generated successfully."
    )
    print(
        f"Output file: {output_file}"
    )
    print(
        f"Main category: {main_category}"
    )
    print(
        f"Specific category: {category}"
    )
    print(
        f"Slug: {slug}"
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
