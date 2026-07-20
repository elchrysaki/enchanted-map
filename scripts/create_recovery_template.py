#!/usr/bin/env python3
# Create an editable, unverified opportunity template from raw submission data.

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urlparse

import yaml


ISSUE_NUMBER = int(os.environ["ISSUE_NUMBER"])
RAW_SUBMISSION_FILE = Path(os.environ["RAW_SUBMISSION_FILE"])
OPPORTUNITIES_DIRECTORY = Path(
    os.environ.get("OPPORTUNITIES_DIRECTORY", "opportunities")
)
NORMAL_OPPORTUNITY_FILE = os.environ.get(
    "NORMAL_OPPORTUNITY_FILE", ""
).strip()
RECOVERY_REASON = os.environ.get(
    "RECOVERY_REASON", "automated research or generation did not produce a page"
).strip()


def fail(message: str) -> NoReturn:
    print(f"::error::{message}")
    raise SystemExit(1)


def write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        print(f"{name}={value}")
        return
    with open(output_path, "a", encoding="utf-8") as output:
        output.write(f"{name}={value}\n")


def clean(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    result = " ".join(value.split())
    return result or None


def clean_list(value: Any) -> list[str]:
    values: list[str]
    if isinstance(value, list):
        values = [str(item) for item in value]
    elif isinstance(value, str):
        checked = re.findall(
            r"^\s*-\s*\[[xX]\]\s*(.+?)\s*$",
            value,
            flags=re.MULTILINE,
        )
        if checked:
            values = checked
        else:
            values = re.split(r"[\n,;•]+", value)
    else:
        return []

    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        item = " ".join(item.split()).strip()
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def slugify(value: Any) -> str:
    text = clean(value) or ""
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:120]


def safe_slug(value: Any, fallback: str) -> str:
    candidate = slugify(value) or fallback
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", candidate):
        return fallback
    return candidate


def valid_url(value: Any) -> str | None:
    text = clean(value)
    if not text:
        return None
    try:
        parsed = urlparse(text)
    except ValueError:
        return None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        return None
    return text


def normalized_date(value: Any) -> str | None:
    text = clean(value)
    if not text:
        return None
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return None
    return parsed.isoformat() if parsed.isoformat() == text else None


def normalized_format(value: Any) -> str:
    text = (clean(value) or "").casefold()
    if "hybrid" in text:
        return "hybrid"
    if "travell" in text or "traveling" in text:
        return "travelling"
    if "multiple" in text:
        return "multiple-formats"
    if "online" in text or "virtual" in text:
        return "online"
    if "person" in text or "onsite" in text or "on-site" in text:
        return "in-person"
    return "not-confirmed"


def read_raw_record() -> dict[str, Any]:
    if not RAW_SUBMISSION_FILE.exists():
        fail(f"Raw submission file does not exist: {RAW_SUBMISSION_FILE}")
    try:
        data = json.loads(RAW_SUBMISSION_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"Could not read raw submission: {exc}")
    if not isinstance(data, dict):
        fail("Raw submission record must be a JSON object.")
    if data.get("schema_version") != 2:
        fail("Recovery templates require a schema-version-2 raw submission.")
    if data.get("record_type") != "raw-submission":
        fail("Recovery input is not a raw-submission record.")
    return data


def routing_list(routing: dict[str, Any], *keys: str) -> list[str]:
    for key in keys:
        values = clean_list(routing.get(key))
        if values:
            return values
    return []


def raw_list(raw: dict[str, Any], *keys: str) -> list[str]:
    for key in keys:
        values = clean_list(raw.get(key))
        if values:
            return values
    return []


def choose_path(main_category: str, slug: str) -> Path:
    destination = OPPORTUNITIES_DIRECTORY / main_category / f"{slug}.md"
    if not destination.exists():
        return destination
    return (
        OPPORTUNITIES_DIRECTORY
        / main_category
        / f"{slug}-issue-{ISSUE_NUMBER}.md"
    )


def markdown_value(value: Any) -> str:
    text = clean(value)
    return text if text else "_Not provided_"


def build_template(record: dict[str, Any]) -> tuple[Path, str]:
    raw = record.get("raw_submission")
    routing = record.get("routing_hints")
    issue = record.get("issue")
    moderation = record.get("moderation")

    if not isinstance(raw, dict):
        raw = {}
    if not isinstance(routing, dict):
        routing = {}
    if not isinstance(issue, dict):
        issue = {}
    if not isinstance(moderation, dict):
        moderation = {}

    title = (
        clean(raw.get("opportunity_name"))
        or clean(issue.get("title"))
        or f"Opportunity from issue {ISSUE_NUMBER}"
    )
    organizer = clean(raw.get("organizer")) or "Not confirmed"

    main_category = safe_slug(
        routing.get("main_category") or raw.get("main_category"),
        "other",
    )
    category = safe_slug(
        routing.get("category") or raw.get("category"),
        "other",
    )
    slug = safe_slug(title, f"opportunity-{ISSUE_NUMBER}")

    opportunity_format = normalized_format(
        raw.get("opportunity_format") or raw.get("format")
    )
    host_country = clean(raw.get("host_country"))
    host_city = clean(raw.get("host_city"))
    host_location = clean(raw.get("host_location"))
    location_display = host_location or ", ".join(
        part for part in (host_city, host_country) if part
    ) or None

    deadline_raw = clean(raw.get("application_deadline"))
    start_raw = clean(raw.get("start_date"))
    end_raw = clean(raw.get("end_date"))

    geographic_regions = routing_list(
        routing, "eligible_regions", "geographic_regions"
    ) or raw_list(raw, "geographic_eligibility")
    eligible_countries = routing_list(
        routing, "eligible_countries"
    ) or raw_list(raw, "eligible_countries")
    academic_levels = routing_list(
        routing, "academic_levels"
    ) or raw_list(raw, "academic_levels")
    broad_fields = routing_list(
        routing, "broad_fields", "academic_fields"
    ) or raw_list(raw, "broad_fields")
    specific_majors = routing_list(
        routing, "specific_majors", "subjects"
    ) or raw_list(raw, "specific_majors")
    audience_groups = routing_list(
        routing, "audiences", "audience_groups"
    )
    funding_features = routing_list(
        routing, "funding_features"
    ) or raw_list(raw, "funding")

    official_page = valid_url(raw.get("official_website"))
    application_page = valid_url(raw.get("application_link"))

    missing_fields = clean_list(moderation.get("missing_required_fields"))
    initial_warnings = clean_list(moderation.get("initial_warnings"))

    summary = clean(raw.get("short_description"))
    funding_details = clean(raw.get("funding_details"))
    eligibility_details = clean(raw.get("eligibility_details"))
    activities = raw_list(raw, "activities")
    benefits = raw_list(raw, "benefits")
    selection_process = clean(raw.get("selection_process"))
    additional_information = clean(raw.get("additional_information"))
    source_notes = clean(raw.get("source_notes"))

    generated_at = datetime.now(timezone.utc).isoformat()
    issue_url = valid_url(issue.get("url"))

    front_matter: dict[str, Any] = {
        "schema_version": 2,
        "record_type": "opportunity",
        "title": title,
        "slug": slug,
        "organizer": organizer,
        "main_category": main_category,
        "category": category,
        "edition": None,
        "status": "pending-review",
        "summary": summary,
        "format": opportunity_format,
        "location": {
            "display": location_display,
            "host_city": host_city,
            "host_country": host_country,
            "host_country_code": None,
            "additional_locations": raw_list(raw, "additional_locations"),
        },
        "dates": {
            "application_deadline": {
                "raw": deadline_raw,
                "display": deadline_raw,
                "normalized": normalized_date(deadline_raw),
            },
            "start_date": {
                "display": start_raw,
                "normalized": normalized_date(start_raw),
            },
            "end_date": {
                "display": end_raw,
                "normalized": normalized_date(end_raw),
            },
            "additional_dates": [],
        },
        "eligibility": {
            "geographic_regions": geographic_regions,
            "eligible_countries": eligible_countries,
            "nationality_or_residency_rules": clean(
                raw.get("nationality_residency_rules")
                or raw.get("nationality_or_residency_rules")
            ),
            "academic_levels": academic_levels,
            "broad_fields": broad_fields,
            "specific_majors": specific_majors,
            "age_requirements": clean(raw.get("age_requirements")),
            "experience_requirements": clean(
                raw.get("experience_requirements")
                or raw.get("required_skills")
            ),
            "language_requirements": clean(raw.get("language_requirements")),
            "display_points": (
                [eligibility_details] if eligibility_details else []
            ),
        },
        "audience": {
            "classification_source": "submitted-dropdown-only",
            "groups": audience_groups,
            "access_model": "not-confirmed",
            "display_points": [],
        },
        "funding": {
            "application_fee": clean(raw.get("application_fee")),
            "participation_fee": clean(raw.get("participation_fee")),
            "scholarship": None,
            "travel_support": None,
            "accommodation": None,
            "meals": None,
            "stipend_or_salary": None,
            "prizes": None,
            "visa_support": None,
            "accessibility_support": None,
            "other_support": [funding_details] if funding_details else [],
            "display_points": [funding_details] if funding_details else [],
        },
        "application": {
            "official_page": official_page,
            "application_page": application_page,
            "requirements": [],
            "documents": [],
            "selection_process": selection_process,
        },
        "program": {
            "activities": activities,
            "benefits": benefits,
            "topics": [],
        },
        "filters": {
            "main_categories": [main_category],
            "categories": [category],
            "formats": [opportunity_format],
            "host_countries": [host_country] if host_country else [],
            "eligible_regions": geographic_regions,
            "eligible_countries": eligible_countries,
            "academic_levels": academic_levels,
            "academic_fields": broad_fields,
            "subjects": specific_majors,
            "audience_groups": audience_groups,
            "funding_features": funding_features,
            "topics": [],
        },
        "tags": [],
        "verification": {
            "human_review_required": True,
            "human_review_completed": False,
            "safe_to_generate_draft_page": False,
            "research_confidence": 0,
            "research_recommended_action": "manual-research-needed",
            "formatter_recommended_action": (
                "recovery-template-needs-human-edit"
            ),
            "automatically_verified": False,
            "automatically_published": False,
        },
        "submission": {
            "issue_number": ISSUE_NUMBER,
            "issue_url": issue_url,
            "submitted_by": clean(issue.get("author")),
        },
        "recovery": {
            "mode": "raw-submission-template",
            "template": True,
            "ready_for_publication": False,
            "human_verified": False,
            "reason": RECOVERY_REASON,
            "generated_at": generated_at,
            "source": "preserved-raw-submission-only",
            "missing_required_fields": missing_fields,
            "initial_warnings": initial_warnings,
        },
        "provenance": {
            "generated_at": generated_at,
            "generator": "scripts/create_recovery_template.py",
            "raw_submission_file": str(RAW_SUBMISSION_FILE),
            "research_bypassed_for_template": True,
            "official_evidence_verified": False,
        },
    }

    body_lines = [
        "# " + title,
        "",
        "> [!CAUTION]",
        "> **Recovery template. This page has not been researched or verified.**",
        "> It was created only from the contributor's preserved submission so a",
        "> human moderator can correct and complete it instead of starting from",
        "> an empty file.",
        "",
        "## Submitted overview",
        "",
        summary or "_No short description was supplied._",
        "",
        "## Submitted information",
        "",
        f"- **Organizer:** {markdown_value(raw.get('organizer'))}",
        f"- **Official source:** {markdown_value(raw.get('official_website'))}",
        f"- **Application link:** {markdown_value(raw.get('application_link'))}",
        f"- **Deadline:** {markdown_value(raw.get('application_deadline'))}",
        f"- **Format:** {markdown_value(raw.get('opportunity_format'))}",
        f"- **Location:** {markdown_value(location_display)}",
        f"- **Eligibility notes:** {markdown_value(eligibility_details)}",
        f"- **Funding notes:** {markdown_value(funding_details)}",
        "",
        "## Moderator work required",
        "",
        "- [ ] Open and verify the official source.",
        "- [ ] Correct every unsupported or outdated claim.",
        "- [ ] Complete missing dates, eligibility, funding, and application data.",
        "- [ ] Confirm the main and specific category pair.",
        "- [ ] Keep submitted audience groups unchanged unless the submitter edits them.",
        "- [ ] Make every `filters` list exactly mirror its source field.",
        "- [ ] Remove this recovery warning after the page is complete.",
        "",
        "Only after completing those checks, change the front matter to:",
        "",
        "```yaml",
        "recovery:",
        "  mode: raw-submission-template",
        "  template: false",
        "  ready_for_publication: true",
        "  human_verified: true",
        "```",
        "",
        "The merge remains the final human approval. This template cannot approve",
        "or publish itself, despite software's recurring delusions of competence.",
    ]

    if additional_information:
        body_lines.extend(
            ["", "## Additional submitted information", "", additional_information]
        )
    if source_notes:
        body_lines.extend(["", "## Submitted source notes", "", source_notes])

    yaml_text = yaml.safe_dump(
        front_matter,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).rstrip()
    content = "---\n" + yaml_text + "\n---\n\n" + "\n".join(body_lines) + "\n"
    return choose_path(main_category, slug), content


def main() -> None:
    if NORMAL_OPPORTUNITY_FILE:
        normal_path = Path(NORMAL_OPPORTUNITY_FILE)
        if normal_path.exists() and normal_path.is_file():
            write_output("opportunity_file", str(normal_path))
            write_output("recovery_template_created", "false")
            print("Normal generated opportunity exists; recovery template skipped.")
            return

    record = read_raw_record()
    destination, content = build_template(record)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8", newline="\n")

    write_output("opportunity_file", destination.as_posix())
    write_output("recovery_template_created", "true")
    print(f"Created editable recovery opportunity template: {destination}")


if __name__ == "__main__":
    main()
