from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = ROOT / "data" / "opportunities.json"
README_FILE = ROOT / "README.md"

START_MARKER = "<!-- CLOSING_SOON_START -->"
END_MARKER = "<!-- CLOSING_SOON_END -->"

MAX_ITEMS = 5
CLOSING_SOON_DAYS = 30

TABLE_HEADER = """| Status | Category | Opportunity | Focus | When & Where | Format | Funding / Prize | Eligibility | Apply | Deadline |
|---|---|---|---|---|---|---|---|---|---|"""


def clean(value: Any) -> str:
    if value is None:
        return ""

    text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace("|", "\\|")


def nested(record: dict[str, Any], *keys: str) -> Any:
    value: Any = record

    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)

    return value


def parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None

    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def titleize(value: Any) -> str:
    text = clean(value).replace("-", " ")
    return text.title()


def first_items(
    value: Any,
    *,
    maximum: int = 2,
) -> list[str]:
    if not isinstance(value, list):
        return []

    result: list[str] = []

    for item in value:
        cleaned = clean(item)
        if cleaned:
            result.append(cleaned)

        if len(result) >= maximum:
            break

    return result


def join_items(
    value: Any,
    *,
    maximum: int = 2,
) -> str:
    return "; ".join(
        first_items(value, maximum=maximum)
    )


def focus_text(record: dict[str, Any]) -> str:
    topics = join_items(
        nested(record, "program", "topics"),
        maximum=2,
    )
    if topics:
        return topics

    fields = join_items(
        nested(record, "eligibility", "broad_fields"),
        maximum=2,
    )
    if fields:
        return fields

    return titleize(record.get("category")) or "General"


def date_range_text(record: dict[str, Any]) -> str:
    start = clean(
        nested(record, "dates", "start_date", "display")
    )
    end = clean(
        nested(record, "dates", "end_date", "display")
    )

    if start and end and start != end:
        return f"{start} – {end}"

    return start or end


def location_text(record: dict[str, Any]) -> str:
    display = clean(
        nested(record, "location", "display")
    )
    if display:
        return display

    city = clean(
        nested(record, "location", "host_city")
    )
    country = clean(
        nested(record, "location", "host_country")
    )

    return ", ".join(
        value for value in (city, country) if value
    )


def when_where_text(record: dict[str, Any]) -> str:
    parts = [
        part
        for part in (
            date_range_text(record),
            location_text(record),
        )
        if part
    ]

    return " · ".join(parts) or "Not confirmed"


def funding_text(record: dict[str, Any]) -> str:
    display_points = join_items(
        nested(record, "funding", "display_points"),
        maximum=2,
    )
    if display_points:
        return display_points

    filter_features = join_items(
        nested(record, "filters", "funding_features"),
        maximum=2,
    )
    if filter_features:
        return filter_features

    funding = record.get("funding")
    if not isinstance(funding, dict):
        return "Not stated"

    labels = {
        "application_fee": "Application fee",
        "participation_fee": "Participation fee",
        "scholarship": "Scholarship available",
        "travel_support": "Travel support",
        "accommodation": "Accommodation support",
        "meals": "Meals included",
        "stipend_or_salary": "Stipend or salary",
        "prizes": "Prize available",
    }

    found: list[str] = []

    for key, label in labels.items():
        value = funding.get(key)

        if value not in (None, "", [], {}, False):
            found.append(label)

        if len(found) >= 2:
            break

    return "; ".join(found) or "Not stated"


def eligibility_text(record: dict[str, Any]) -> str:
    display_points = join_items(
        nested(record, "eligibility", "display_points"),
        maximum=2,
    )
    if display_points:
        return display_points

    levels = first_items(
        nested(record, "eligibility", "academic_levels"),
        maximum=3,
    )
    if levels:
        return ", ".join(titleize(level) for level in levels)

    return "See official eligibility"


def opportunity_link(record: dict[str, Any]) -> str:
    title = clean(record.get("title")) or "View opportunity"
    path = clean(record.get("path"))

    if not path:
        return title

    return f"[{title}]({path})"


def application_link(record: dict[str, Any]) -> str:
    application_url = clean(
        nested(record, "application", "application_page")
    )
    official_url = clean(
        nested(record, "application", "official_page")
    )

    url = application_url or official_url

    if not url:
        return "View page"

    return f"[Apply]({url})"


def row_for(record: dict[str, Any]) -> str:
    return "| " + " | ".join(
        [
            "🔥 Closing soon",
            titleize(record.get("category")),
            opportunity_link(record),
            focus_text(record),
            when_where_text(record),
            titleize(record.get("format")),
            funding_text(record),
            eligibility_text(record),
            application_link(record),
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
            ),
        ]
    ) + " |"


def select_closing_soon(
    opportunities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    today = datetime.now().astimezone().date()
    final_day = today + timedelta(
        days=CLOSING_SOON_DAYS
    )

    eligible: list[dict[str, Any]] = []

    for record in opportunities:
        if record.get("status") != "published":
            continue

        deadline = parse_date(
            nested(
                record,
                "dates",
                "application_deadline",
                "normalized",
            )
        )

        if deadline is None:
            continue

        if not today <= deadline <= final_day:
            continue

        copied = dict(record)
        copied["_closing_deadline"] = deadline
        eligible.append(copied)

    eligible.sort(
        key=lambda item: (
            item["_closing_deadline"],
            clean(item.get("title")).lower(),
        )
    )

    selected: list[dict[str, Any]] = []
    used_categories: set[str] = set()

    # First pass: favour category variety.
    for record in eligible:
        main_category = clean(
            record.get("main_category")
        )

        if main_category in used_categories:
            continue

        selected.append(record)
        used_categories.add(main_category)

        if len(selected) >= MAX_ITEMS:
            break

    # Second pass: fill remaining places by deadline.
    if len(selected) < MAX_ITEMS:
        selected_ids = {
            clean(record.get("id"))
            or clean(record.get("path"))
            for record in selected
        }

        for record in eligible:
            record_id = (
                clean(record.get("id"))
                or clean(record.get("path"))
            )

            if record_id in selected_ids:
                continue

            selected.append(record)
            selected_ids.add(record_id)

            if len(selected) >= MAX_ITEMS:
                break

    selected.sort(
        key=lambda item: (
            item["_closing_deadline"],
            clean(item.get("title")).lower(),
        )
    )

    return selected


def build_table(
    opportunities: list[dict[str, Any]],
) -> str:
    selected = select_closing_soon(opportunities)

    if not selected:
        empty_row = (
            "| _No published opportunities are closing "
            "within the next 30 days._ | — | — | — | — | "
            "— | — | — | "
            "[Add a discovery]"
            "(https://github.com/elchrysaki/"
            "offmap-hub/issues/new?"
            "template=submit-opportunity.yml) | — |"
        )

        return f"{TABLE_HEADER}\n{empty_row}"

    rows = "\n".join(row_for(record) for record in selected)

    return f"{TABLE_HEADER}\n{rows}"


def replace_section(
    readme: str,
    replacement: str,
) -> str:
    if START_MARKER not in readme:
        raise SystemExit(
            f"Missing marker in README.md: {START_MARKER}"
        )

    if END_MARKER not in readme:
        raise SystemExit(
            f"Missing marker in README.md: {END_MARKER}"
        )

    before, remaining = readme.split(
        START_MARKER,
        1,
    )
    _, after = remaining.split(
        END_MARKER,
        1,
    )

    return (
        before
        + START_MARKER
        + "\n\n"
        + replacement.rstrip()
        + "\n\n"
        + END_MARKER
        + after
    )


def main() -> None:
    if not INDEX_FILE.exists():
        raise SystemExit(
            f"Central opportunity index not found: {INDEX_FILE}"
        )

    if not README_FILE.exists():
        raise SystemExit(
            f"README not found: {README_FILE}"
        )

    index = json.loads(
        INDEX_FILE.read_text(encoding="utf-8")
    )

    opportunities = index.get("opportunities")

    if not isinstance(opportunities, list):
        raise SystemExit(
            "data/opportunities.json does not contain "
            "an opportunities list."
        )

    readme = README_FILE.read_text(
        encoding="utf-8"
    )

    updated = replace_section(
        readme,
        build_table(opportunities),
    )

    README_FILE.write_text(
        updated,
        encoding="utf-8",
        newline="\n",
    )

    chosen = select_closing_soon(opportunities)

    print(
        "Updated README Closing Soon section with "
        f"{len(chosen)} opportunity/opportunities."
    )


if __name__ == "__main__":
    main()
