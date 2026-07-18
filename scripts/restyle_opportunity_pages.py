from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from opportunity_document import (
    OpportunityDocumentError,
    parse_opportunity_document,
    render_opportunity_document,
)


ROOT = Path(__file__).resolve().parents[1]
OPPORTUNITIES = ROOT / "opportunities"
STYLE_MARKER = "<!-- offmap-public-page-v2 -->"

SECTION_MAP = {
    "opportunity overview": "overview",
    "why this opportunity is worth your attention": "overview",
    "organizer": "organizer",
    "meet the organizer": "organizer",
    "who can apply": "who_can_apply",
    "location & format": "location_and_format",
    "where and how it happens": "location_and_format",
    "important dates": "important_dates",
    "dates to remember": "important_dates",
    "funding & support": "funding_and_support",
    "fees, funding and support": "funding_and_support",
    "how to apply": "application_path",
    "what participants do": "what_participants_do",
    "what you will do": "what_participants_do",
}

MOJIBAKE = {
    "ð§­": "🧭",
    "ð": "🔗",
    "ð": "🚀",
    "ð": "📍",
    "ðï¸": "🗓️",
    "ð¸": "💸",
    "ð ï¸": "🛠️",
    "ð¥": "👥",
    "ðï¸": "🏛️",
    "â†’": "→",
    "Â·": "·",
}


def fix_mojibake(value: str) -> str:
    for broken, repaired in MOJIBAKE.items():
        value = value.replace(broken, repaired)
    return value


def safe_inline(value: Any, fallback: str = "Not confirmed") -> str:
    if not isinstance(value, str) or not value.strip():
        return fallback
    cleaned = " ".join(value.split())
    return html.escape(cleaned, quote=False)


def safe_block(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return html.escape(value.strip(), quote=False)


def label(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "Opportunity"
    return value.replace("-", " ").title()


def extract_sections(body: str) -> dict[str, str]:
    body = fix_mojibake(body)
    sections: dict[str, str] = {}
    pattern = re.compile(
        r"^##\s+(.+?)\s*$\n(.*?)(?=^##\s+|^---\s*$|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    for heading, content in pattern.findall(body):
        normalized = re.sub(r"[^a-z0-9& ]+", "", heading.casefold()).strip()
        key = SECTION_MAP.get(normalized)
        if key and content.strip():
            sections[key] = content.strip()
    return sections


def synchronize_filters(metadata: dict[str, Any]) -> None:
    filters = metadata.get("filters")
    location = metadata.get("location")
    eligibility = metadata.get("eligibility")
    audience = metadata.get("audience")
    program = metadata.get("program")

    if not isinstance(filters, dict):
        return

    filters["main_categories"] = [metadata.get("main_category")]
    filters["categories"] = [metadata.get("category")]
    filters["formats"] = [metadata.get("format")]

    if isinstance(location, dict):
        host_country = location.get("host_country")
        filters["host_countries"] = [host_country] if host_country else []

    if isinstance(eligibility, dict):
        filters["eligible_regions"] = list(eligibility.get("geographic_regions") or [])
        filters["eligible_countries"] = list(eligibility.get("eligible_countries") or [])
        filters["academic_levels"] = list(eligibility.get("academic_levels") or [])
        filters["academic_fields"] = list(eligibility.get("broad_fields") or [])
        filters["subjects"] = list(eligibility.get("specific_majors") or [])

    if isinstance(audience, dict):
        filters["audience_groups"] = list(audience.get("groups") or [])

    if isinstance(program, dict):
        filters["topics"] = list(program.get("topics") or [])


def add_section(lines: list[str], heading: str, content: str | None) -> None:
    if not content:
        return
    lines.extend([f"## {heading}", "", safe_block(content), ""])


def build_body(metadata: dict[str, Any], old_body: str) -> str:
    sections = extract_sections(old_body)

    title = safe_inline(metadata.get("title"), "Untitled opportunity")
    organizer = safe_inline(metadata.get("organizer"), "Organizer not confirmed")
    summary = safe_block(metadata.get("summary"))
    category = safe_inline(label(metadata.get("category")))
    opportunity_format = safe_inline(label(metadata.get("format")))

    location = metadata.get("location")
    location_display = (
        safe_inline(location.get("display"))
        if isinstance(location, dict)
        else "Not confirmed"
    )

    deadline = "Not confirmed"
    program_dates = "Not confirmed"
    dates = metadata.get("dates")
    if isinstance(dates, dict):
        deadline_field = dates.get("application_deadline")
        if isinstance(deadline_field, dict):
            deadline = safe_inline(deadline_field.get("display"))

        start = dates.get("start_date")
        end = dates.get("end_date")
        start_text = safe_inline(start.get("display"), "") if isinstance(start, dict) else ""
        end_text = safe_inline(end.get("display"), "") if isinstance(end, dict) else ""
        if start_text and end_text:
            program_dates = f"{start_text} to {end_text}"
        else:
            program_dates = start_text or end_text or "Not confirmed"

    application = metadata.get("application")
    official_page = application.get("official_page") if isinstance(application, dict) else None
    application_page = application.get("application_page") if isinstance(application, dict) else None

    lines = [
        STYLE_MARKER,
        f"# 🧭 {title}",
        "",
        f"**{organizer}**",
        "",
        f"🎯 **{category}** · 💻 **{opportunity_format}** · 📍 **{location_display}**",
        "",
    ]

    links: list[str] = []
    if isinstance(official_page, str) and official_page.strip():
        links.append(f"**[🌐 Official page]({official_page.strip()})**")
    if isinstance(application_page, str) and application_page.strip():
        links.append(f"**[🚀 Apply now]({application_page.strip()})**")
    if links:
        lines.extend([" · ".join(links), ""])

    if summary:
        lines.extend(["> [!TIP]"])
        lines.extend(f"> {line}" for line in summary.splitlines())
        lines.append("")

    lines.extend(
        [
            "> [!IMPORTANT]",
            f"> **Application deadline:** {deadline}  ",
            f"> **Program dates:** {program_dates}  ",
            f"> **Location:** {location_display}  ",
            f"> **Format:** {opportunity_format}",
            "",
            "---",
            "",
        ]
    )

    add_section(lines, "✨ Why this opportunity is worth your attention", sections.get("overview"))
    add_section(lines, "🏛️ Meet the organizer", sections.get("organizer"))
    add_section(lines, "👥 Who can apply", sections.get("who_can_apply"))
    add_section(lines, "📍 Where and how it happens", sections.get("location_and_format"))
    add_section(lines, "🗓️ Dates to remember", sections.get("important_dates"))
    add_section(lines, "💸 Fees, funding and support", sections.get("funding_and_support"))
    add_section(lines, "🛠️ What you will do", sections.get("what_participants_do"))
    add_section(lines, "🚀 How to apply", sections.get("application_path"))

    if links:
        lines.extend(["## 🔗 Official links", ""])
        if isinstance(official_page, str) and official_page.strip():
            lines.append(f"- **[🌐 Explore the official page]({official_page.strip()})**")
        if isinstance(application_page, str) and application_page.strip():
            lines.append(f"- **[🚀 Start your application]({application_page.strip()})**")
        lines.append("")

    submission = metadata.get("submission")
    issue_url = submission.get("issue_url") if isinstance(submission, dict) else None
    if isinstance(issue_url, str) and issue_url.strip():
        lines.extend(
            [
                "---",
                "",
                "<details>",
                "<summary><strong>🧾 Research and review trail</strong></summary>",
                "",
                "This page was prepared from a community submission, checked against official sources, and routed through human moderator review before publication.",
                "",
                f"- [View the original submission]({issue_url.strip()})",
                "",
                "</details>",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    changed = 0
    for path in sorted(OPPORTUNITIES.rglob("*.md")):
        if path.name.casefold() == "readme.md":
            continue

        try:
            metadata, body = parse_opportunity_document(
                path.read_text(encoding="utf-8")
            )
        except (OSError, OpportunityDocumentError) as exc:
            print(f"Skipping {path.relative_to(ROOT)}: {exc}")
            continue

        if metadata.get("record_type") != "opportunity":
            continue

        synchronize_filters(metadata)
        new_body = body if STYLE_MARKER in body else build_body(metadata, body)
        new_text = render_opportunity_document(metadata, new_body)

        if new_text != path.read_text(encoding="utf-8"):
            path.write_text(new_text, encoding="utf-8")
            changed += 1
            print(f"Restyled {path.relative_to(ROOT)}")

    print(f"Restyled opportunity pages: {changed}")


if __name__ == "__main__":
    main()
