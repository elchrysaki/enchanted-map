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


ROOT = Path(__file__).resolve().parents[1]
OPPORTUNITIES_DIR = ROOT / "opportunities"
DATA_DIR = ROOT / "data"
JSON_INDEX = DATA_DIR / "opportunities.json"
MARKDOWN_INDEX = OPPORTUNITIES_DIR / "README.md"

FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)
PUBLIC_STATUS = "published"

CATEGORY_ORDER = [
    "conference",
    "hackathon",
    "competition",
    "academy",
    "summer-school",
    "fellowship",
    "research-program",
    "exchange-program",
    "internship",
    "workshop-seminar",
    "bootcamp",
    "startup-program",
    "scholarship",
    "grant",
    "volunteering-program",
    "leadership-program",
    "cultural-program",
    "other",
]

CATEGORY_TITLES = {
    "conference": "🎤 Conferences & Summits",
    "hackathon": "💻 Hackathons & Build Challenges",
    "competition": "🏆 Competitions & Challenges",
    "academy": "🏛️ Academies",
    "summer-school": "☀️ Summer & Winter Schools",
    "fellowship": "🤝 Fellowships",
    "research-program": "🔬 Research Programs",
    "exchange-program": "🌍 Exchange Programs",
    "internship": "🧰 Internships",
    "workshop-seminar": "🧠 Workshops & Seminars",
    "bootcamp": "⚡ Bootcamps",
    "startup-program": "🚀 Startup Programs",
    "scholarship": "🎓 Scholarships",
    "grant": "💰 Grants",
    "volunteering-program": "❤️ Volunteering Programs",
    "leadership-program": "🧭 Leadership Programs",
    "cultural-program": "🎭 Cultural Programs",
    "other": "✨ Other Opportunities",
}


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
    result = " ".join(str(value).split())
    return result or None


def nested(record: dict[str, Any], *keys: str) -> Any:
    value: Any = record
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def valid_url(value: Any) -> str | None:
    candidate = clean(value)
    if not candidate:
        return None
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return candidate


def humanize(value: str) -> str:
    return value.replace("-", " ").replace("_", " ").title()


def list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        item_text = clean(item)
        if item_text and item_text.casefold() not in seen:
            seen.add(item_text.casefold())
            result.append(item_text)
    return result


def cell(value: Any, fallback: str = "Not confirmed") -> str:
    return (
        (clean(value) or fallback)
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\n", " ")
    )


def link(label: str, target: str) -> str:
    safe_label = label.replace("[", "\\[").replace("]", "\\]")
    safe_target = target.replace(" ", "%20").replace(")", "%29")
    return f"[{safe_label}]({safe_target})"


def parse_file(path: Path) -> dict[str, Any]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        fail(f"Could not read {path}: {exc}")

    match = FRONT_MATTER.match(content)
    if not match:
        fail(f"{path} does not begin with YAML front matter.")

    try:
        record = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        fail(f"Invalid YAML in {path}: {exc}")

    if not isinstance(record, dict):
        fail(f"Front matter in {path} must be a YAML object.")

    return json_safe(record)


def category_rank(category: str) -> int:
    try:
        return CATEGORY_ORDER.index(category)
    except ValueError:
        return len(CATEGORY_ORDER)


def validate_published(path: Path, record: dict[str, Any]) -> None:
    for field in ("title", "slug", "category", "status"):
        if not clean(record.get(field)):
            fail(f"Published opportunity {path} is missing '{field}'.")

    category = clean(record.get("category"))
    if category != path.parent.name:
        fail(
            f"Category mismatch in {path}: front matter says '{category}', "
            f"but its folder is '{path.parent.name}'."
        )

    official = valid_url(nested(record, "application", "official_page"))
    application = valid_url(
        nested(record, "application", "application_page")
    )
    if not official and not application:
        fail(f"Published opportunity {path} has no valid official URL.")


def load_records() -> tuple[list[dict[str, Any]], Counter[str]]:
    OPPORTUNITIES_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(
        path
        for path in OPPORTUNITIES_DIR.rglob("*.md")
        if path.name.lower() != "readme.md"
    )

    records: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    seen_slugs: dict[str, Path] = {}
    seen_urls: dict[str, Path] = {}

    for path in files:
        record = parse_file(path)
        status = clean(record.get("status")) or "unknown"
        status_counts[status] += 1

        if status != PUBLIC_STATUS:
            warn(f"Skipping {path}; status is '{status}'.")
            continue

        validate_published(path, record)

        slug = clean(record.get("slug"))
        assert slug is not None
        slug_key = slug.casefold()
        if slug_key in seen_slugs:
            fail(
                f"Duplicate slug '{slug}' in {path} and "
                f"{seen_slugs[slug_key]}."
            )
        seen_slugs[slug_key] = path

        official = valid_url(
            nested(record, "application", "official_page")
        )
        if official:
            url_key = official.rstrip("/").casefold()
            if url_key in seen_urls:
                warn(
                    f"Possible duplicate URL in {path} and "
                    f"{seen_urls[url_key]}."
                )
            else:
                seen_urls[url_key] = path

        record["path"] = path.relative_to(ROOT).as_posix()
        records.append(record)

    records.sort(
        key=lambda item: (
            category_rank(clean(item.get("category")) or "other"),
            clean(
                nested(
                    item,
                    "dates",
                    "application_deadline",
                    "normalized",
                )
            )
            or "9999-12-31",
            (clean(item.get("title")) or "").casefold(),
        )
    )
    return records, status_counts


def build_json(
    records: list[dict[str, Any]],
    status_counts: Counter[str],
) -> str:
    categories = Counter(
        clean(record.get("category")) or "other"
        for record in records
    )
    payload = {
        "schema_version": 1,
        "source": "opportunities/**/*.md",
        "public_status": PUBLIC_STATUS,
        "total_published": len(records),
        "category_counts": dict(sorted(categories.items())),
        "source_status_counts": dict(sorted(status_counts.items())),
        "opportunities": records,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def deadline(record: dict[str, Any]) -> str:
    return (
        clean(nested(record, "dates", "application_deadline", "display"))
        or clean(
            nested(record, "dates", "application_deadline", "normalized")
        )
        or clean(nested(record, "dates", "application_deadline", "raw"))
        or "Not confirmed"
    )


def location(record: dict[str, Any]) -> str:
    display = clean(nested(record, "location", "display"))
    if display:
        return display

    city = clean(nested(record, "location", "host_city"))
    country = clean(nested(record, "location", "host_country"))
    combined = ", ".join(item for item in (city, country) if item)
    if combined:
        return combined

    return "Online" if clean(record.get("format")) == "online" else "Not confirmed"


def funding(record: dict[str, Any]) -> str:
    features = list_of_strings(
        nested(record, "filters", "funding_features")
    )
    if features:
        return ", ".join(humanize(item) for item in features[:3])

    fields = [
        ("Scholarship", nested(record, "funding", "scholarship")),
        ("Travel Support", nested(record, "funding", "travel_support")),
        ("Accommodation", nested(record, "funding", "accommodation")),
        ("Stipend", nested(record, "funding", "stipend")),
        ("Salary", nested(record, "funding", "salary")),
        ("Prizes", nested(record, "funding", "prizes")),
    ]
    present = [
        label
        for label, value in fields
        if clean(value)
        and clean(value).casefold()
        not in {"none", "no", "not available", "not confirmed"}
    ]
    return ", ".join(present[:3]) or "Not confirmed"


def eligibility(record: dict[str, Any]) -> str:
    levels = list_of_strings(
        nested(record, "filters", "academic_levels")
        or nested(record, "eligibility", "academic_levels")
    )
    regions = list_of_strings(
        nested(record, "filters", "eligible_regions")
        or nested(record, "eligibility", "geographic_regions")
    )
    values = [humanize(item) for item in levels[:2] + regions[:1]]
    return ", ".join(values) or "See opportunity page"


def quest_link(record: dict[str, Any]) -> str:
    title = clean(record.get("title")) or "Untitled Opportunity"
    path = Path(clean(record.get("path")) or "")
    relative = path.relative_to("opportunities").as_posix()
    return link(title, relative)


def application_link(record: dict[str, Any]) -> str:
    application = valid_url(
        nested(record, "application", "application_page")
    )
    official = valid_url(
        nested(record, "application", "official_page")
    )
    if application:
        return link("Apply", application)
    if official:
        return link("Official page", official)
    return "Not confirmed"


def build_markdown(records: list[dict[str, Any]]) -> str:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[clean(record.get("category")) or "other"].append(record)

    lines = [
        "# 🗺️ Opportunity Index",
        "",
        (
            "This page is generated automatically from reviewed opportunity "
            "files. Edit the individual quest pages, not this index."
        ),
        "",
        f"**Published opportunities:** {len(records)}",
        "",
    ]

    if not records:
        lines.extend(["> No published opportunities are indexed yet.", ""])
        return "\n".join(lines)

    lines.extend(["## Jump to a category", ""])
    for category in sorted(grouped, key=category_rank):
        title = CATEGORY_TITLES.get(category, f"✨ {humanize(category)}")
        lines.append(f"- [{title}](#{category}) ({len(grouped[category])})")
    lines.append("")

    for category in sorted(grouped, key=category_rank):
        title = CATEGORY_TITLES.get(category, f"✨ {humanize(category)}")
        lines.extend(
            [
                f'<a id="{category}"></a>',
                "",
                f"## {title}",
                "",
                (
                    "| Opportunity | Organizer | Deadline | Format | "
                    "Location | Funding | Eligibility | Application |"
                ),
                "|---|---|---|---|---|---|---|---|",
            ]
        )

        for record in grouped[category]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        quest_link(record),
                        cell(record.get("organizer")),
                        cell(deadline(record)),
                        cell(humanize(clean(record.get("format")) or "")),
                        cell(location(record)),
                        cell(funding(record)),
                        cell(eligibility(record)),
                        application_link(record),
                    ]
                )
                + " |"
            )

        lines.extend(["", "[↑ Back to categories](#jump-to-a-category)", ""])

    lines.extend(
        [
            "---",
            "",
            (
                "_Generated by `scripts/build_indexes.py`. Always verify "
                "deadlines and eligibility on the official page._"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    records, status_counts = load_records()

    atomic_write(JSON_INDEX, build_json(records, status_counts))
    atomic_write(MARKDOWN_INDEX, build_markdown(records))

    print("Opportunity indexes rebuilt successfully.")
    print(f"Published opportunities: {len(records)}")
    print(f"JSON index: {JSON_INDEX.relative_to(ROOT)}")
    print(f"Markdown index: {MARKDOWN_INDEX.relative_to(ROOT)}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
