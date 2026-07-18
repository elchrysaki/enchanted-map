from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


# ============================================================
# PATHS AND INDEX SETTINGS
# ============================================================

ROOT = Path(__file__).resolve().parents[1]
OPPORTUNITIES_DIR = ROOT / "opportunities"
DATA_DIR = ROOT / "data"

JSON_INDEX = DATA_DIR / "opportunities.json"
MARKDOWN_INDEX = OPPORTUNITIES_DIR / "README.md"

FRONT_MATTER = re.compile(
    r"^---\s*\n(.*?)\n---\s*(?:\n|$)",
    re.DOTALL,
)

PUBLIC_STATUS = "published"
MAX_URL_LENGTH = 2_000
MAX_LIST_ITEMS = 100
MAX_TAGS = 20

ALLOWED_SCHEMES = {"http", "https"}

MAIN_CATEGORY_ORDER = [
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
]

MAIN_CATEGORY_TITLES = {
    "events": "🎤 Events",
    "internships": "🧰 Internships",
    "competitions": "🏆 Competitions",
    "research": "🔬 Research",
    "fellowships": "🤝 Fellowships",
    "scholarships": "🎓 Scholarships & Grants",
    "courses": "📚 Courses & Schools",
    "innovation": "🚀 Innovation & Startups",
    "creative-calls": "🎨 Creative Calls",
    "exchanges": "🌍 Exchanges & Mobility",
    "volunteering": "❤️ Volunteering",
    "other": "✨ Other Opportunities",
}

SPECIFIC_CATEGORY_ORDER = [
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
]

ALLOWED_MAIN_CATEGORIES = set(MAIN_CATEGORY_ORDER)
ALLOWED_SPECIFIC_CATEGORIES = set(SPECIFIC_CATEGORY_ORDER)

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


# ============================================================
# ERRORS AND BASIC HELPERS
# ============================================================

def fail(message: str) -> None:
    print(f"::error::{message}")
    raise SystemExit(1)


def warn(message: str) -> None:
    print(f"::warning::{message}")


def clean(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, (date, datetime)):
        return value.isoformat()

    if not isinstance(value, str):
        return None

    result = " ".join(value.split())
    return result or None


def nested(
    record: dict[str, Any],
    *keys: str,
) -> Any:
    value: Any = record

    for key in keys:
        if not isinstance(value, dict):
            return None

        value = value.get(key)

    return value


def require_object(
    parent: dict[str, Any],
    key: str,
    *,
    context: str,
) -> dict[str, Any]:
    value = parent.get(key)

    if not isinstance(value, dict):
        fail(
            f"{context}: '{key}' must be a YAML object."
        )

    return value


def require_string(
    parent: dict[str, Any],
    key: str,
    *,
    context: str,
) -> str:
    value = clean(parent.get(key))

    if value is None:
        fail(
            f"{context}: '{key}' must contain text."
        )

    return value


def optional_string(
    parent: dict[str, Any],
    key: str,
    *,
    context: str,
) -> str | None:
    value = parent.get(key)

    if value is None:
        return None

    cleaned = clean(value)

    if cleaned is None:
        fail(
            f"{context}: '{key}' must be a string or null."
        )

    return cleaned


def require_string_list(
    parent: dict[str, Any],
    key: str,
    *,
    context: str,
    maximum: int = MAX_LIST_ITEMS,
) -> list[str]:
    value = parent.get(key)

    if not isinstance(value, list):
        fail(
            f"{context}: '{key}' must be a YAML list."
        )

    if len(value) > maximum:
        fail(
            f"{context}: '{key}' contains too many values. "
            f"Maximum: {maximum}."
        )

    result: list[str] = []

    for index, item in enumerate(value):
        cleaned = clean(item)

        if cleaned is None:
            fail(
                f"{context}: '{key}[{index}]' must "
                "contain text."
            )

        result.append(cleaned)

    return result


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            json_safe(item)
            for item in value
        ]

    if isinstance(value, (date, datetime)):
        return value.isoformat()

    return value


def validated_url(
    value: Any,
    field_name: str,
    *,
    required: bool = False,
) -> str | None:
    if value is None:
        if required:
            fail(f"'{field_name}' must contain a URL.")
        return None

    if not isinstance(value, str):
        fail(f"'{field_name}' must be a string or null.")

    candidate = value.strip()

    if not candidate:
        fail(f"'{field_name}' must not be empty.")

    if len(candidate) > MAX_URL_LENGTH:
        fail(f"'{field_name}' exceeds the URL length limit.")

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
        fail(f"'{field_name}' is not a valid URL: {exc}")

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        fail(f"'{field_name}' must use HTTP or HTTPS.")

    if not parsed.hostname:
        fail(f"'{field_name}' must include a hostname.")

    if parsed.username or parsed.password:
        fail(f"'{field_name}' must not contain credentials.")

    if port not in (None, 80, 443):
        fail(
            f"'{field_name}' must not use a non-standard port."
        )

    return candidate


def humanize(value: str) -> str:
    return value.replace(
        "-",
        " ",
    ).replace(
        "_",
        " ",
    ).title()


def display_unique_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    result: list[str] = []
    seen: set[str] = set()

    for item in value:
        item_text = clean(item)

        if not item_text:
            continue

        key = item_text.casefold()

        if key in seen:
            continue

        seen.add(key)
        result.append(item_text)

    return result


def markdown_cell(
    value: Any,
    fallback: str = "Not confirmed",
) -> str:
    result = clean(value) or fallback

    return (
        result.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("\n", " ")
    )


def markdown_link(
    label: str,
    target: str,
) -> str:
    safe_label = (
        label.replace("\\", "\\\\")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )

    return f"[{safe_label}](<{target}>)"


# ============================================================
# FRONT MATTER PARSING
# ============================================================

def parse_file(path: Path) -> dict[str, Any]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        fail(f"Could not read {path}: {exc}")

    match = FRONT_MATTER.match(content)

    if not match:
        fail(
            f"{path} does not begin with YAML front matter."
        )

    try:
        record = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        fail(f"Invalid YAML in {path}: {exc}")

    if not isinstance(record, dict):
        fail(
            f"Front matter in {path} must be a YAML object."
        )

    safe_record = json_safe(record)

    if not isinstance(safe_record, dict):
        fail(
            f"Front matter in {path} could not be normalized."
        )

    return safe_record


# ============================================================
# SCHEMA VALIDATION
# ============================================================

def validate_category_pair(
    main_category: str,
    category: str,
    *,
    context: str,
) -> None:
    if main_category not in ALLOWED_MAIN_CATEGORIES:
        fail(
            f"{context}: invalid main category "
            f"'{main_category}'."
        )

    if category not in ALLOWED_SPECIFIC_CATEGORIES:
        fail(
            f"{context}: invalid specific category "
            f"'{category}'."
        )

    if category == "other":
        return

    expected = SPECIFIC_CATEGORIES_BY_MAIN.get(
        main_category,
        set(),
    )

    if category not in expected:
        fail(
            f"{context}: category '{category}' does not "
            f"belong under '{main_category}'."
        )


def validate_iso_date(
    value: Any,
    field_name: str,
) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        fail(
            f"'{field_name}' must be a string or null."
        )

    try:
        parsed = datetime.strptime(
            value,
            "%Y-%m-%d",
        ).date()
    except ValueError:
        fail(
            f"'{field_name}' must use a real YYYY-MM-DD date."
        )

    if parsed.isoformat() != value:
        fail(
            f"'{field_name}' must use zero-padded YYYY-MM-DD."
        )

    return value


def validate_filter_mirror(
    filters: dict[str, Any],
    filter_name: str,
    expected: list[str],
    *,
    context: str,
) -> None:
    actual = require_string_list(
        filters,
        filter_name,
        context=context,
    )

    if actual != expected:
        fail(
            f"{context}: filters.{filter_name} must exactly "
            f"match its source field, including order."
        )


def validate_published(
    path: Path,
    record: dict[str, Any],
) -> None:
    context = str(path)

    if record.get("schema_version") != 2:
        fail(
            f"{context}: published records must use "
            "schema version 2."
        )

    if record.get("record_type") != "opportunity":
        fail(
            f"{context}: record_type must be 'opportunity'."
        )

    title = require_string(
        record,
        "title",
        context=context,
    )
    slug = require_string(
        record,
        "slug",
        context=context,
    )
    main_category = require_string(
        record,
        "main_category",
        context=context,
    )
    category = require_string(
        record,
        "category",
        context=context,
    )
    status = require_string(
        record,
        "status",
        context=context,
    )
    opportunity_format = require_string(
        record,
        "format",
        context=context,
    )

    if status != PUBLIC_STATUS:
        fail(
            f"{context}: validate_published received "
            f"status '{status}'."
        )

    if len(title) > 300:
        fail(
            f"{context}: title exceeds 300 characters."
        )

    if slug != path.stem:
        fail(
            f"{context}: front-matter slug '{slug}' does "
            f"not match filename '{path.stem}'."
        )

    relative_path = path.relative_to(
        OPPORTUNITIES_DIR
    )

    if len(relative_path.parts) != 2:
        fail(
            f"{context}: opportunity files must use exactly "
            "opportunities/<main_category>/<slug>.md."
        )

    if main_category != path.parent.name:
        fail(
            f"{context}: main_category is '{main_category}', "
            f"but the folder is '{path.parent.name}'."
        )

    validate_category_pair(
        main_category,
        category,
        context=context,
    )

    if opportunity_format not in ALLOWED_FORMATS:
        fail(
            f"{context}: invalid format "
            f"'{opportunity_format}'."
        )

    location = require_object(
        record,
        "location",
        context=context,
    )
    host_country = optional_string(
        location,
        "host_country",
        context=f"{context} location",
    )
    host_country_code = optional_string(
        location,
        "host_country_code",
        context=f"{context} location",
    )

    if (
        host_country_code is not None
        and (
            len(host_country_code) != 2
            or not host_country_code.isalpha()
        )
    ):
        fail(
            f"{context}: location.host_country_code must "
            "be a two-letter code or null."
        )

    require_string_list(
        location,
        "additional_locations",
        context=f"{context} location",
        maximum=50,
    )

    dates = require_object(
        record,
        "dates",
        context=context,
    )

    for field_name in (
        "application_deadline",
        "start_date",
        "end_date",
    ):
        date_object = require_object(
            dates,
            field_name,
            context=f"{context} dates",
        )

        validate_iso_date(
            date_object.get("normalized"),
            f"{context} dates.{field_name}.normalized",
        )

    additional_dates = dates.get("additional_dates")

    if not isinstance(additional_dates, list):
        fail(
            f"{context}: dates.additional_dates must be a list."
        )

    eligibility = require_object(
        record,
        "eligibility",
        context=context,
    )
    geographic_regions = require_string_list(
        eligibility,
        "geographic_regions",
        context=f"{context} eligibility",
    )
    eligible_countries = require_string_list(
        eligibility,
        "eligible_countries",
        context=f"{context} eligibility",
    )
    academic_levels = require_string_list(
        eligibility,
        "academic_levels",
        context=f"{context} eligibility",
    )
    broad_fields = require_string_list(
        eligibility,
        "broad_fields",
        context=f"{context} eligibility",
    )
    specific_majors = require_string_list(
        eligibility,
        "specific_majors",
        context=f"{context} eligibility",
    )

    audience = require_object(
        record,
        "audience",
        context=context,
    )

    if (
        audience.get("classification_source")
        != "submitted-dropdown-only"
    ):
        fail(
            f"{context}: audience.classification_source "
            "must be 'submitted-dropdown-only'."
        )

    audience_groups = require_string_list(
        audience,
        "groups",
        context=f"{context} audience",
    )

    access_model = require_string(
        audience,
        "access_model",
        context=f"{context} audience",
    )

    if access_model not in ALLOWED_AUDIENCE_ACCESS_MODELS:
        fail(
            f"{context}: invalid audience.access_model "
            f"'{access_model}'."
        )

    funding = require_object(
        record,
        "funding",
        context=context,
    )
    require_string_list(
        funding,
        "other_support",
        context=f"{context} funding",
    )

    application = require_object(
        record,
        "application",
        context=context,
    )

    official = validated_url(
        application.get("official_page"),
        f"{context} application.official_page",
    )
    application_url = validated_url(
        application.get("application_page"),
        f"{context} application.application_page",
    )

    if not official and not application_url:
        fail(
            f"{context}: published opportunities need at least "
            "one valid official or application URL."
        )

    program = require_object(
        record,
        "program",
        context=context,
    )
    topics = require_string_list(
        program,
        "topics",
        context=f"{context} program",
    )

    filters = require_object(
        record,
        "filters",
        context=context,
    )

    validate_filter_mirror(
        filters,
        "main_categories",
        [main_category],
        context=context,
    )
    validate_filter_mirror(
        filters,
        "categories",
        [category],
        context=context,
    )
    validate_filter_mirror(
        filters,
        "formats",
        [opportunity_format],
        context=context,
    )
    validate_filter_mirror(
        filters,
        "host_countries",
        [host_country] if host_country else [],
        context=context,
    )
    validate_filter_mirror(
        filters,
        "eligible_regions",
        geographic_regions,
        context=context,
    )
    validate_filter_mirror(
        filters,
        "eligible_countries",
        eligible_countries,
        context=context,
    )
    validate_filter_mirror(
        filters,
        "academic_levels",
        academic_levels,
        context=context,
    )
    validate_filter_mirror(
        filters,
        "academic_fields",
        broad_fields,
        context=context,
    )
    validate_filter_mirror(
        filters,
        "subjects",
        specific_majors,
        context=context,
    )
    validate_filter_mirror(
        filters,
        "audience_groups",
        audience_groups,
        context=context,
    )
    validate_filter_mirror(
        filters,
        "topics",
        topics,
        context=context,
    )

    require_string_list(
        filters,
        "funding_features",
        context=context,
    )

    require_string_list(
        record,
        "tags",
        context=context,
        maximum=MAX_TAGS,
    )

    verification = require_object(
        record,
        "verification",
        context=context,
    )

    if verification.get("human_review_required") is not True:
        fail(
            f"{context}: verification.human_review_required "
            "must remain true."
        )

    if (
        verification.get("safe_to_generate_draft_page")
        is not True
    ):
        fail(
            f"{context}: published record was not marked safe "
            "to generate."
        )

    if verification.get("automatically_published") is not False:
        fail(
            f"{context}: verification.automatically_published "
            "must remain false."
        )

    submission = require_object(
        record,
        "submission",
        context=context,
    )
    issue_number = submission.get("issue_number")

    if (
        not isinstance(issue_number, int)
        or isinstance(issue_number, bool)
        or issue_number <= 0
    ):
        fail(
            f"{context}: submission.issue_number must be "
            "a positive integer."
        )


# ============================================================
# RECORD LOADING
# ============================================================

def main_category_rank(value: str) -> int:
    try:
        return MAIN_CATEGORY_ORDER.index(value)
    except ValueError:
        return len(MAIN_CATEGORY_ORDER)


def specific_category_rank(value: str) -> int:
    try:
        return SPECIFIC_CATEGORY_ORDER.index(value)
    except ValueError:
        return len(SPECIFIC_CATEGORY_ORDER)


def normalized_deadline(
    record: dict[str, Any],
) -> str:
    value = nested(
        record,
        "dates",
        "application_deadline",
        "normalized",
    )

    return clean(value) or "9999-12-31"


def canonical_url_key(value: str) -> str:
    parsed = urlparse(value)

    host = (parsed.hostname or "").casefold()
    port = parsed.port

    if (
        port is None
        or (
            parsed.scheme.casefold() == "http"
            and port == 80
        )
        or (
            parsed.scheme.casefold() == "https"
            and port == 443
        )
    ):
        authority = host
    else:
        authority = f"{host}:{port}"

    path = parsed.path.rstrip("/") or "/"

    return (
        f"{parsed.scheme.casefold()}://{authority}"
        f"{path}?{parsed.query}"
    ).rstrip("?")


def load_records(
) -> tuple[list[dict[str, Any]], Counter[str]]:
    OPPORTUNITIES_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    files = sorted(
        path
        for path in OPPORTUNITIES_DIR.rglob("*.md")
        if path.name.casefold() != "readme.md"
    )

    records: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()

    seen_routes: dict[str, Path] = {}
    seen_issue_numbers: dict[int, Path] = {}
    seen_urls: dict[str, Path] = {}

    for path in files:
        record = parse_file(path)
        status = clean(record.get("status")) or "unknown"
        status_counts[status] += 1

        if status != PUBLIC_STATUS:
            warn(
                f"Skipping {path.relative_to(ROOT)}; "
                f"status is '{status}'."
            )
            continue

        validate_published(
            path,
            record,
        )

        main_category = require_string(
            record,
            "main_category",
            context=str(path),
        )
        slug = require_string(
            record,
            "slug",
            context=str(path),
        )

        route_key = (
            f"{main_category}/{slug}"
        ).casefold()

        if route_key in seen_routes:
            fail(
                f"Duplicate route '{main_category}/{slug}' "
                f"in {path} and {seen_routes[route_key]}."
            )

        seen_routes[route_key] = path

        issue_number = nested(
            record,
            "submission",
            "issue_number",
        )

        if not isinstance(issue_number, int):
            fail(
                f"{path}: missing valid submission issue number."
            )

        if issue_number in seen_issue_numbers:
            fail(
                f"Duplicate submission issue #{issue_number} "
                f"in {path} and "
                f"{seen_issue_numbers[issue_number]}."
            )

        seen_issue_numbers[issue_number] = path

        for field_name in (
            "official_page",
            "application_page",
        ):
            url = validated_url(
                nested(
                    record,
                    "application",
                    field_name,
                ),
                f"{path} application.{field_name}",
            )

            if not url:
                continue

            url_key = canonical_url_key(url)

            if url_key in seen_urls:
                warn(
                    f"Possible duplicate URL in "
                    f"{path.relative_to(ROOT)} and "
                    f"{seen_urls[url_key].relative_to(ROOT)}."
                )
            else:
                seen_urls[url_key] = path

        relative_path = path.relative_to(ROOT).as_posix()

        record["id"] = f"{main_category}:{slug}"
        record["path"] = relative_path
        records.append(record)

    records.sort(
        key=lambda item: (
            main_category_rank(
                clean(item.get("main_category"))
                or "other"
            ),
            specific_category_rank(
                clean(item.get("category"))
                or "other"
            ),
            normalized_deadline(item),
            (
                clean(item.get("title"))
                or ""
            ).casefold(),
        )
    )

    return records, status_counts


# ============================================================
# JSON INDEX
# ============================================================

def build_json(
    records: list[dict[str, Any]],
    status_counts: Counter[str],
) -> str:
    main_category_counts = Counter(
        clean(record.get("main_category"))
        or "other"
        for record in records
    )
    category_counts = Counter(
        clean(record.get("category"))
        or "other"
        for record in records
    )

    nested_category_counts: dict[
        str,
        Counter[str],
    ] = defaultdict(Counter)

    for record in records:
        main_category = (
            clean(record.get("main_category"))
            or "other"
        )
        category = (
            clean(record.get("category"))
            or "other"
        )
        nested_category_counts[
            main_category
        ][category] += 1

    payload = {
        "schema_version": 2,
        "record_type": "opportunity-index",
        "source": "opportunities/*/*.md",
        "public_status": PUBLIC_STATUS,
        "total_published": len(records),
        "main_category_counts": dict(
            sorted(
                main_category_counts.items(),
                key=lambda item: (
                    main_category_rank(item[0]),
                    item[0],
                ),
            )
        ),
        "category_counts": dict(
            sorted(
                category_counts.items(),
                key=lambda item: (
                    specific_category_rank(item[0]),
                    item[0],
                ),
            )
        ),
        "main_category_category_counts": {
            main_category: dict(
                sorted(
                    counts.items(),
                    key=lambda item: (
                        specific_category_rank(
                            item[0]
                        ),
                        item[0],
                    ),
                )
            )
            for main_category, counts in sorted(
                nested_category_counts.items(),
                key=lambda item: (
                    main_category_rank(item[0]),
                    item[0],
                ),
            )
        },
        "source_status_counts": dict(
            sorted(status_counts.items())
        ),
        "opportunities": records,
    }

    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


# ============================================================
# MARKDOWN INDEX
# ============================================================

def display_deadline(
    record: dict[str, Any],
) -> str:
    return (
        clean(
            nested(
                record,
                "dates",
                "application_deadline",
                "display",
            )
        )
        or clean(
            nested(
                record,
                "dates",
                "application_deadline",
                "normalized",
            )
        )
        or clean(
            nested(
                record,
                "dates",
                "application_deadline",
                "raw",
            )
        )
        or "Not confirmed"
    )


def display_location(
    record: dict[str, Any],
) -> str:
    display = clean(
        nested(
            record,
            "location",
            "display",
        )
    )

    if display:
        return display

    city = clean(
        nested(
            record,
            "location",
            "host_city",
        )
    )
    country = clean(
        nested(
            record,
            "location",
            "host_country",
        )
    )

    combined = ", ".join(
        item
        for item in (
            city,
            country,
        )
        if item
    )

    if combined:
        return combined

    if clean(record.get("format")) == "online":
        return "Online"

    return "Not confirmed"


def meaningful_support(value: Any) -> bool:
    cleaned = clean(value)

    if not cleaned:
        return False

    return cleaned.casefold() not in {
        "none",
        "no",
        "not available",
        "not confirmed",
        "unknown",
        "n/a",
    }


def display_funding(
    record: dict[str, Any],
) -> str:
    features = display_unique_strings(
        nested(
            record,
            "filters",
            "funding_features",
        )
    )

    if features:
        return ", ".join(
            humanize(item)
            for item in features[:3]
        )

    fields = [
        (
            "Scholarship",
            nested(
                record,
                "funding",
                "scholarship",
            ),
        ),
        (
            "Travel Support",
            nested(
                record,
                "funding",
                "travel_support",
            ),
        ),
        (
            "Accommodation",
            nested(
                record,
                "funding",
                "accommodation",
            ),
        ),
        (
            "Meals",
            nested(
                record,
                "funding",
                "meals",
            ),
        ),
        (
            "Stipend or Salary",
            nested(
                record,
                "funding",
                "stipend_or_salary",
            ),
        ),
        (
            "Prizes",
            nested(
                record,
                "funding",
                "prizes",
            ),
        ),
    ]

    present = [
        label
        for label, value in fields
        if meaningful_support(value)
    ]

    return (
        ", ".join(present[:3])
        or "Not confirmed"
    )


def display_eligibility(
    record: dict[str, Any],
) -> str:
    levels = display_unique_strings(
        nested(
            record,
            "filters",
            "academic_levels",
        )
    )
    regions = display_unique_strings(
        nested(
            record,
            "filters",
            "eligible_regions",
        )
    )
    audiences = display_unique_strings(
        nested(
            record,
            "filters",
            "audience_groups",
        )
    )

    values = [
        humanize(item)
        for item in (
            levels[:2]
            + regions[:1]
            + audiences[:1]
        )
    ]

    return (
        ", ".join(values)
        or "See opportunity page"
    )


def opportunity_link(
    record: dict[str, Any],
) -> str:
    title = (
        clean(record.get("title"))
        or "Untitled Opportunity"
    )

    path_value = clean(record.get("path"))

    if not path_value:
        fail(
            f"Indexed opportunity '{title}' has no path."
        )

    path = Path(path_value)

    try:
        relative = path.relative_to(
            "opportunities"
        ).as_posix()
    except ValueError:
        fail(
            f"Indexed opportunity '{title}' has an "
            f"invalid path: {path_value}"
        )

    return markdown_link(
        title,
        relative,
    )


def application_link(
    record: dict[str, Any],
) -> str:
    application_url = nested(
        record,
        "application",
        "application_page",
    )
    official_url = nested(
        record,
        "application",
        "official_page",
    )

    if isinstance(application_url, str):
        return markdown_link(
            "Apply",
            application_url,
        )

    if isinstance(official_url, str):
        return markdown_link(
            "Official page",
            official_url,
        )

    return "Not confirmed"


def build_markdown(
    records: list[dict[str, Any]],
) -> str:
    grouped: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)

    for record in records:
        grouped[
            clean(
                record.get("main_category")
            )
            or "other"
        ].append(record)

    lines = [
        "# 🗺️ OffMap Opportunity Index",
        "",
        (
            "This index is generated automatically from reviewed "
            "opportunity files. Edit the individual opportunity "
            "pages, not this index."
        ),
        "",
        f"**Published opportunities:** {len(records)}",
        "",
    ]

    if not records:
        lines.extend(
            [
                "> No published opportunities are indexed yet.",
                "",
            ]
        )

        return "\n".join(lines)

    lines.extend(
        [
            "## Jump to a main category",
            "",
        ]
    )

    for main_category in sorted(
        grouped,
        key=main_category_rank,
    ):
        title = MAIN_CATEGORY_TITLES.get(
            main_category,
            f"✨ {humanize(main_category)}",
        )
        anchor = f"main-{main_category}"

        lines.append(
            f"- [{title}](#{anchor}) "
            f"({len(grouped[main_category])})"
        )

    lines.append("")

    for main_category in sorted(
        grouped,
        key=main_category_rank,
    ):
        title = MAIN_CATEGORY_TITLES.get(
            main_category,
            f"✨ {humanize(main_category)}",
        )
        anchor = f"main-{main_category}"

        lines.extend(
            [
                f'<a id="{anchor}"></a>',
                "",
                f"## {title}",
                "",
                (
                    "| Opportunity | Type | Organizer | Deadline | "
                    "Format | Location | Funding | Eligibility | "
                    "Application |"
                ),
                (
                    "|---|---|---|---|---|---|---|---|---|"
                ),
            ]
        )

        for record in grouped[main_category]:
            category = (
                clean(record.get("category"))
                or "other"
            )
            opportunity_format = (
                clean(record.get("format"))
                or "not-confirmed"
            )

            lines.append(
                "| "
                + " | ".join(
                    [
                        opportunity_link(record),
                        markdown_cell(
                            humanize(category)
                        ),
                        markdown_cell(
                            record.get("organizer")
                        ),
                        markdown_cell(
                            display_deadline(record)
                        ),
                        markdown_cell(
                            humanize(
                                opportunity_format
                            )
                        ),
                        markdown_cell(
                            display_location(record)
                        ),
                        markdown_cell(
                            display_funding(record)
                        ),
                        markdown_cell(
                            display_eligibility(record)
                        ),
                        application_link(record),
                    ]
                )
                + " |"
            )

        lines.extend(
            [
                "",
                (
                    "[↑ Back to main categories]"
                    "(#jump-to-a-main-category)"
                ),
                "",
            ]
        )

    lines.extend(
        [
            "---",
            "",
            (
                "_Generated by `scripts/build_indexes.py`. "
                "Always verify deadlines, eligibility, and "
                "application details on the official page._"
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
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    records, status_counts = load_records()

    atomic_write(
        JSON_INDEX,
        build_json(
            records,
            status_counts,
        ),
    )
    atomic_write(
        MARKDOWN_INDEX,
        build_markdown(records),
    )

    print(
        "OffMap opportunity indexes rebuilt successfully."
    )
    print(
        f"Published opportunities: {len(records)}"
    )
    print(
        "JSON index: "
        f"{JSON_INDEX.relative_to(ROOT)}"
    )
    print(
        "Markdown index: "
        f"{MARKDOWN_INDEX.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
