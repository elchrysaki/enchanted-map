from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
import yaml

API_URL = "https://api.github.com"
TOKEN = os.environ["GITHUB_TOKEN"]
REPOSITORY = os.environ["REPOSITORY"]
ISSUE_NUMBER = int(os.environ["ISSUE_NUMBER"])

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

COMMENT_MARKER = "<!-- enchanted-map-intake -->"

FIELD_LABELS = {
    "opportunity_name": "✨ Opportunity name",
    "category": "⚔️ Quest category",
    "organizer": "🏰 Organizer",
    "short_description": "📖 What is this quest?",
    "official_website": "🔗 Official opportunity page",
    "application_link": "🚪 Direct application portal",
    "opportunity_format": "🧭 Quest format",
    "host_city": "🏙️ Host city",
    "host_country": "🌍 Host country",
    "additional_locations": "🗺️ Additional locations",
    "application_deadline": "⏳ Application deadline",
    "start_date": "🌅 Start date",
    "end_date": "🌙 End date",
    "date_notes": "📆 Additional date information",
    "geographic_eligibility": "🌐 Geographic eligibility",
    "eligible_countries": "🏳️ Eligible countries",
    "nationality_residency_rules": "🛂 Nationality or residency requirements",
    "academic_levels": "🎓 Eligible academic levels",
    "broad_fields": "🔬 Broad academic fields",
    "specific_majors": "🧠 Relevant majors and specializations",
    "required_skills": "🛠️ Required skills or experience",
    "audience_access": "🔐 Audience access model",
    "audience_groups": "🧑‍🤝‍🧑 Intended, encouraged, priority, or eligible groups",
    "audience_details": "📜 Exact audience or inclusion wording",
    "audience_source": "🔎 Source for audience information",
    "funding": "💰 Funding, costs, and support",
    "participation_fee": "💳 Application or participation fee",
    "funding_details": "🎒 Funding details",
    "activities": "⚒️ Main activities",
    "benefits": "🎁 Quest rewards",
    "selection_process": "🏹 Selection process",
    "keywords": "🏷️ Search keywords",
    "career_themes": "🧭 Career and opportunity themes",
    "source_notes": "📚 Verification notes",
    "supporting_files": "📎 Supporting files",
}

CATEGORY_MAP = {
    "conference": "conference",
    "hackathon": "hackathon",
    "competition": "competition",
    "fellowship": "fellowship",
    "academy": "academy",
    "scholarship": "scholarship",
    "research program": "research-program",
    "exchange program": "exchange-program",
    "summer school": "summer-school",
    "internship": "internship",
    "workshop or seminar": "workshop-seminar",
    "bootcamp": "bootcamp",
    "startup program": "startup-program",
    "grant": "grant",
    "volunteering program": "volunteering-program",
    "leadership program": "leadership-program",
    "cultural program": "cultural-program",
    "other": "other",
}

FORMAT_MAP = {
    "in person": "in-person",
    "online": "online",
    "hybrid": "hybrid",
    "multiple formats": "multiple-formats",
    "not confirmed": "not-confirmed",
}

AUDIENCE_ACCESS_MAP = {
    "open to everyone with no specified priority group": "none",
    "open to everyone but actively encourages specified groups": "encouraged",
    "preference or priority is given to specified groups": "priority",
    "reserved exclusively for specified groups": "exclusive",
    "audience focus is mentioned but eligibility is unclear": "focus-unclear",
    "not confirmed": "not-confirmed",
}

LABEL_DEFINITIONS = {
    "new-discovery": {
        "color": "8B5CF6",
        "description": "A newly submitted opportunity.",
    },
    "needs-review": {
        "color": "F4C542",
        "description": "Requires human review before publication.",
    },
    "intake-parsed": {
        "color": "7C3AED",
        "description": "The submission form was parsed successfully.",
    },
}


def github_request(
    method: str,
    endpoint: str,
    *,
    expected: tuple[int, ...] = (200,),
    **kwargs: Any,
) -> requests.Response:
    response = requests.request(
        method,
        f"{API_URL}{endpoint}",
        headers=HEADERS,
        timeout=30,
        **kwargs,
    )
    if response.status_code not in expected:
        raise RuntimeError(
            f"GitHub API {method} {endpoint} failed with "
            f"{response.status_code}: {response.text}"
        )
    return response


def clean_text(value: str | None) -> str:
    if value is None:
        return ""
    value = value.strip()
    if value in {"_No response_", "No response", "N/A", "n/a"}:
        return ""
    return value


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value.lower()).strip("-")
    return slug


def extract_field(body: str, label: str) -> str:
    known_headings = "|".join(
        re.escape(item) for item in FIELD_LABELS.values()
    )
    pattern = re.compile(
        rf"^###\s+{re.escape(label)}\s*$\n"
        rf"(.*?)"
        rf"(?=^###\s+(?:{known_headings})\s*$|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(body)
    return clean_text(match.group(1) if match else "")


def parse_selected(value: str) -> list[str]:
    value = clean_text(value)
    if not value:
        return []

    checked = re.findall(r"^\s*-\s*\[[xX]\]\s*(.+?)\s*$", value, re.MULTILINE)
    if checked:
        return [item.strip() for item in checked if item.strip()]

    without_bullets = re.sub(r"^\s*[-*]\s+", "", value, flags=re.MULTILINE)
    parts = re.split(r"[\n,;]+", without_bullets)
    return [
        part.strip()
        for part in parts
        if clean_text(part.strip())
        and not re.match(r"^\[[ xX]\]$", part.strip())
    ]


def parse_lines(value: str) -> list[str]:
    return parse_selected(value)


def normalize_list(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        slug = slugify(value)
        if slug and slug not in seen:
            seen.add(slug)
            result.append(slug)
    return result


def normalize_date(value: str) -> str | None:
    value = clean_text(value)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def valid_http_url(value: str) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def parse_submission(body: str) -> dict[str, str]:
    return {
        key: extract_field(body, label)
        for key, label in FIELD_LABELS.items()
    }


def category_slug(raw_category: str) -> str:
    return CATEGORY_MAP.get(raw_category.strip().lower(), "other")


def mapped_slug(raw_value: str, mapping: dict[str, str]) -> str:
    return mapping.get(raw_value.strip().lower(), slugify(raw_value))


def build_normalized_submission(
    issue: dict[str, Any],
    raw: dict[str, str],
) -> dict[str, Any]:
    geographic_values = parse_selected(raw["geographic_eligibility"])
    academic_levels = parse_selected(raw["academic_levels"])
    broad_fields = parse_selected(raw["broad_fields"])
    majors = parse_lines(raw["specific_majors"])
    audience_groups = parse_selected(raw["audience_groups"])
    funding = parse_selected(raw["funding"])
    career_themes = parse_selected(raw["career_themes"])
    keywords = parse_lines(raw["keywords"])
    eligible_countries = parse_lines(raw["eligible_countries"])

    deadline_iso = normalize_date(raw["application_deadline"])
    start_iso = normalize_date(raw["start_date"])
    end_iso = normalize_date(raw["end_date"])

    warnings: list[str] = []
    contradictions: list[str] = []

    required_fields = {
        "opportunity_name": raw["opportunity_name"],
        "category": raw["category"],
        "organizer": raw["organizer"],
        "short_description": raw["short_description"],
        "official_website": raw["official_website"],
        "opportunity_format": raw["opportunity_format"],
        "host_country": raw["host_country"],
        "application_deadline": raw["application_deadline"],
        "specific_majors": raw["specific_majors"],
        "participation_fee": raw["participation_fee"],
        "source_notes": raw["source_notes"],
    }
    missing = [key for key, value in required_fields.items() if not value]

    if raw["official_website"] and not valid_http_url(raw["official_website"]):
        warnings.append("The official opportunity page is not a valid HTTP/HTTPS URL.")

    if raw["application_link"] and not valid_http_url(raw["application_link"]):
        warnings.append("The direct application portal is not a valid HTTP/HTTPS URL.")

    if raw["audience_source"] and not valid_http_url(raw["audience_source"]):
        warnings.append("The audience source is not a valid HTTP/HTTPS URL.")

    if audience_groups and (
        not raw["audience_details"] or not raw["audience_source"]
    ):
        warnings.append(
            "Audience groups were selected without both supporting wording "
            "and an official audience source."
        )

    audience_access = mapped_slug(raw["audience_access"], AUDIENCE_ACCESS_MAP)
    if audience_access == "none" and audience_groups:
        contradictions.append(
            "The access model says there is no specified priority group, "
            "but audience groups were selected."
        )

    if start_iso and end_iso and date.fromisoformat(end_iso) < date.fromisoformat(start_iso):
        contradictions.append("The end date is earlier than the start date.")

    if deadline_iso and start_iso and date.fromisoformat(deadline_iso) > date.fromisoformat(start_iso):
        warnings.append("The application deadline is later than the start date.")

    category = category_slug(raw["category"])
    opportunity_slug = slugify(raw["opportunity_name"])
    issue_number = issue["number"]

    return {
        "schema_version": 1,
        "source": {
            "repository": REPOSITORY,
            "issue_number": issue_number,
            "issue_url": issue.get("html_url", ""),
            "submitted_by": issue.get("user", {}).get("login", ""),
            "created_at": issue.get("created_at"),
        },
        "identity": {
            "title": raw["opportunity_name"],
            "slug": f"{opportunity_slug}-{issue_number}",
            "category": category,
            "organizer": raw["organizer"],
            "status": "pending-review",
        },
        "links": {
            "official": raw["official_website"],
            "application": raw["application_link"],
            "audience_source": raw["audience_source"],
        },
        "location": {
            "format": mapped_slug(raw["opportunity_format"], FORMAT_MAP),
            "host_city": raw["host_city"],
            "host_country": raw["host_country"],
            "host_country_slug": slugify(raw["host_country"]),
            "additional_locations": parse_lines(raw["additional_locations"]),
        },
        "dates": {
            "application_deadline_raw": raw["application_deadline"],
            "application_deadline": deadline_iso,
            "start_date_raw": raw["start_date"],
            "start_date": start_iso,
            "end_date_raw": raw["end_date"],
            "end_date": end_iso,
            "notes": raw["date_notes"],
        },
        "eligibility": {
            "geographic_raw": geographic_values,
            "geographic_region_slugs": normalize_list(geographic_values),
            "eligible_countries_raw": eligible_countries,
            "eligible_country_slugs": normalize_list(eligible_countries),
            "nationality_residency_rules": raw["nationality_residency_rules"],
            "academic_levels_raw": academic_levels,
            "academic_level_slugs": normalize_list(academic_levels),
            "required_skills": raw["required_skills"],
        },
        "academic": {
            "broad_fields_raw": broad_fields,
            "broad_field_slugs": normalize_list(broad_fields),
            "majors_raw": majors,
            "major_slugs": normalize_list(majors),
        },
        "audience": {
            "access": audience_access,
            "groups_raw": audience_groups,
            "group_slugs": normalize_list(audience_groups),
            "details": raw["audience_details"],
            "source": raw["audience_source"],
        },
        "funding": {
            "types_raw": funding,
            "type_slugs": normalize_list(funding),
            "fee": raw["participation_fee"],
            "details": raw["funding_details"],
        },
        "content": {
            "description": raw["short_description"],
            "activities": raw["activities"],
            "benefits": raw["benefits"],
            "selection_process": raw["selection_process"],
            "source_notes": raw["source_notes"],
            "supporting_files": raw["supporting_files"],
        },
        "search": {
            "keywords_raw": keywords,
            "keyword_slugs": normalize_list(keywords),
            "career_themes_raw": career_themes,
            "career_theme_slugs": normalize_list(career_themes),
        },
        "moderation": {
            "missing_required_fields": missing,
            "warnings": warnings,
            "contradictions": contradictions,
            "human_review_required": True,
            "verified": False,
        },
        "raw_form": raw,
    }


def load_registry() -> dict[str, Any]:
    path = Path(".github/moderators.yml")
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def config_slugs(values: Any) -> set[str]:
    if values is None:
        return set()
    if isinstance(values, str):
        values = [values]
    return {slugify(str(value)) for value in values if str(value).strip()}


def open_review_count(username: str) -> int:
    query = (
        f"repo:{REPOSITORY} is:open assignee:{username} "
        f"label:needs-review"
    )
    try:
        response = github_request(
            "GET",
            "/search/issues",
            params={"q": query, "per_page": 1},
        )
        return int(response.json().get("total_count", 0))
    except RuntimeError:
        return 999


def moderator_score(
    username: str,
    config: dict[str, Any],
    submission: dict[str, Any],
    weights: dict[str, int],
) -> tuple[int, list[str]]:
    specialties = config.get("specialties", {})
    reasons: list[str] = []
    score = 0

    category = submission["identity"]["category"]
    fields = set(submission["academic"]["broad_field_slugs"])
    fields.update(submission["academic"]["major_slugs"])
    audiences = set(submission["audience"]["group_slugs"])
    countries = {submission["location"]["host_country_slug"]}
    regions = set(submission["eligibility"]["geographic_region_slugs"])
    keywords = set(submission["search"]["keyword_slugs"])

    comparisons = [
        ("category", {category}, config_slugs(specialties.get("categories"))),
        (
            "academic_field",
            fields,
            config_slugs(specialties.get("academic_fields")),
        ),
        ("audience", audiences, config_slugs(specialties.get("audiences"))),
        ("country", countries, config_slugs(specialties.get("countries"))),
        ("region", regions, config_slugs(specialties.get("regions"))),
        ("keyword", keywords, config_slugs(specialties.get("keywords"))),
    ]

    for key, submitted_values, moderator_values in comparisons:
        exact_matches = submitted_values & (moderator_values - {"*"})
        if not exact_matches:
            continue

        if key == "keyword":
            points = weights.get(key, 1) * len(exact_matches)
        else:
            points = weights.get(key, 1)

        score += points
        reasons.append(
            f"{key}: {', '.join(sorted(exact_matches))} (+{points})"
        )

    return score, reasons


def select_moderators(
    registry: dict[str, Any],
    submission: dict[str, Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    routing = registry.get("routing", {})
    governance = registry.get("governance", {})
    moderators = registry.get("moderators", {})
    weights = routing.get(
        "score_weights",
        {
            "category": 6,
            "academic_field": 5,
            "audience": 5,
            "country": 4,
            "region": 2,
            "keyword": 1,
        },
    )
    maximum = int(routing.get("max_issue_assignees", 2))

    ranked: list[dict[str, Any]] = []

    for username, config in moderators.items():
        if not config.get("active", True):
            continue

        score, reasons = moderator_score(
            username,
            config,
            submission,
            weights,
        )
        workload = open_review_count(username)
        maximum_workload = int(
            config.get("workload", {}).get("max_open_reviews", 999)
        )

        ranked.append(
            {
                "username": username,
                "score": score,
                "reasons": reasons,
                "open_reviews": workload,
                "max_open_reviews": maximum_workload,
                "available": workload < maximum_workload,
            }
        )

    specialized = [
        item for item in ranked if item["score"] > 0 and item["available"]
    ]
    specialized.sort(
        key=lambda item: (
            -item["score"],
            item["open_reviews"],
            item["username"],
        )
    )

    selected = [item["username"] for item in specialized[:maximum]]

    if not selected:
        fallback = governance.get("fallback_reviewers", [])
        selected = [str(username) for username in fallback[:maximum]]

    return selected, ranked


def ensure_label(name: str, color: str, description: str) -> None:
    owner_repo = REPOSITORY
    encoded_name = requests.utils.quote(name, safe="")
    response = requests.get(
        f"{API_URL}/repos/{owner_repo}/labels/{encoded_name}",
        headers=HEADERS,
        timeout=30,
    )
    if response.status_code == 200:
        return
    if response.status_code != 404:
        raise RuntimeError(
            f"Could not inspect label {name}: "
            f"{response.status_code} {response.text}"
        )

    github_request(
        "POST",
        f"/repos/{owner_repo}/labels",
        expected=(201,),
        json={
            "name": name,
            "color": color,
            "description": description,
        },
    )


def add_labels(labels: list[str]) -> None:
    github_request(
        "POST",
        f"/repos/{REPOSITORY}/issues/{ISSUE_NUMBER}/labels",
        expected=(200,),
        json={"labels": labels},
    )


def assign_issue(usernames: list[str]) -> list[str]:
    if not usernames:
        return []
    try:
        response = github_request(
            "POST",
            f"/repos/{REPOSITORY}/issues/{ISSUE_NUMBER}/assignees",
            expected=(201,),
            json={"assignees": usernames},
        )
    except RuntimeError as error:
        print(f"Warning: moderator assignment failed: {error}")
        return []

    return [
        assignee.get("login", "")
        for assignee in response.json().get("assignees", [])
        if assignee.get("login")
    ]


def table_value(value: Any) -> str:
    if isinstance(value, list):
        text = ", ".join(str(item) for item in value if item)
    else:
        text = str(value or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace("|", "\\|") or "Not confirmed"


def build_intake_comment(
    submission: dict[str, Any],
    assigned: list[str],
) -> str:
    moderation = submission["moderation"]
    missing = moderation["missing_required_fields"]
    warnings = moderation["warnings"]
    contradictions = moderation["contradictions"]

    assigned_text = (
        ", ".join(f"@{username}" for username in assigned)
        if assigned
        else "Fallback administrator review required"
    )

    review_items: list[str] = []
    if missing:
        review_items.append(
            "- **Missing required fields:** "
            + ", ".join(f"`{item}`" for item in missing)
        )
    if warnings:
        review_items.extend(f"- ⚠️ {item}" for item in warnings)
    if contradictions:
        review_items.extend(f"- ❗ {item}" for item in contradictions)
    if not review_items:
        review_items.append(
            "- The structured intake passed the first mechanical checks."
        )

    return f"""{COMMENT_MARKER}
## 🧭 The Guild Has Logged This Discovery

The submission has been converted into structured data and queued for human review.

| Map detail | Submitted information |
|---|---|
| **Quest** | {table_value(submission["identity"]["title"])} |
| **Category** | `{table_value(submission["identity"]["category"])}` |
| **Organizer** | {table_value(submission["identity"]["organizer"])} |
| **Host realm** | {table_value(submission["location"]["host_country"])} |
| **Deadline** | {table_value(submission["dates"]["application_deadline_raw"])} |
| **Relevant majors** | {table_value(submission["academic"]["majors_raw"])} |
| **Audience groups** | {table_value(submission["audience"]["groups_raw"])} |
| **Assigned cartographer(s)** | {assigned_text} |

### 🔍 Initial Checks

{chr(10).join(review_items)}

> This is an automated intake receipt, not verification or publication.  
> The AI scribe and Pull Request generator will run only after the next workflow stage is connected.
"""


def upsert_comment(body: str) -> None:
    response = github_request(
        "GET",
        f"/repos/{REPOSITORY}/issues/{ISSUE_NUMBER}/comments",
        params={"per_page": 100},
    )
    comments = response.json()

    for comment in comments:
        if COMMENT_MARKER in comment.get("body", ""):
            github_request(
                "PATCH",
                f"/repos/{REPOSITORY}/issues/comments/{comment['id']}",
                json={"body": body},
            )
            return

    github_request(
        "POST",
        f"/repos/{REPOSITORY}/issues/{ISSUE_NUMBER}/comments",
        expected=(201,),
        json={"body": body},
    )


def write_output(submission: dict[str, Any]) -> Path:
    base = Path(os.environ.get("RUNNER_TEMP", "build"))
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"opportunity-submission-{ISSUE_NUMBER}.json"

    with path.open("w", encoding="utf-8") as file:
        json.dump(submission, file, ensure_ascii=False, indent=2)

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as output:
            output.write(f"submission_file={path}\n")
            output.write(
                f"category={submission['identity']['category']}\n"
            )
            output.write(
                "moderators="
                + ",".join(submission["routing"]["selected_moderators"])
                + "\n"
            )

    return path


def main() -> None:
    issue = github_request(
        "GET",
        f"/repos/{REPOSITORY}/issues/{ISSUE_NUMBER}",
    ).json()

    body = issue.get("body") or ""
    raw = parse_submission(body)
    submission = build_normalized_submission(issue, raw)

    registry = load_registry()
    selected, ranking = select_moderators(registry, submission)
    assigned = assign_issue(selected)

    submission["routing"] = {
        "selected_moderators": selected,
        "successfully_assigned": assigned,
        "ranking": ranking,
    }

    category_label = f"category: {submission['identity']['category']}"
    category_definition = {
        "color": "6D4AFF",
        "description": (
            "Opportunity category: "
            f"{submission['identity']['category']}."
        ),
    }

    all_labels = {
        **LABEL_DEFINITIONS,
        category_label: category_definition,
    }
    for name, definition in all_labels.items():
        ensure_label(
            name,
            definition["color"],
            definition["description"],
        )

    add_labels(
        [
            "new-discovery",
            "needs-review",
            "intake-parsed",
            category_label,
        ]
    )

    output_path = write_output(submission)
    upsert_comment(build_intake_comment(submission, assigned))

    print(f"Structured submission written to: {output_path}")
    print(json.dumps(submission, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
