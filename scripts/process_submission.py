from __future__ import annotations

import ipaddress
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import requests
import yaml

# ============================================================
# ENVIRONMENT AND SECURITY LIMITS
# ============================================================

GITHUB_API = "https://api.github.com"
TOKEN = os.environ["GITHUB_TOKEN"]
REPOSITORY = os.environ["REPOSITORY"]
ISSUE_NUMBER = int(os.environ["ISSUE_NUMBER"])

OUTPUT_DIRECTORY = Path(
    os.environ.get(
        "OUTPUT_DIRECTORY",
        "artifacts",
    )
)

MODERATOR_FILE = Path(
    os.environ.get(
        "MODERATOR_FILE",
        ".github/moderators.yml",
    )
)

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

# Keep the existing marker so reruns do not create duplicate comments
# on submissions processed before the OFFMAP rename.
INTAKE_COMMENT_MARKER = "<!-- enchanted-map-intake -->"

# The original GitHub issue remains untouched. These limits protect
# workflow memory, artifacts, comments, and later AI calls.
MAX_ISSUE_BODY_LENGTH = 100_000
MAX_FIELD_LENGTH = 20_000
MAX_LIST_ITEMS = 100
MAX_ROUTING_KEYWORDS = 40
MAX_COMMENT_VALUE_LENGTH = 500

# ============================================================
# FINAL FORM FIELD MAP
# ============================================================

# GitHub Issue Forms render the visible labels in the issue body.
# These values must exactly match submit-opportunity.yml.
FIELD_LABELS: dict[str, str] = {
    # Part I: Essential Quest Details
    "opportunity_name": "â¨ Opportunity name",
    "main_category": "ðï¸ Main opportunity category",
    "category": "ð§­ Quest category",
    "organizer": "ð° Organizer",
    "short_description": "ð What is the opportunity?",
    "official_website": "ð Official or most reliable source",
    "application_deadline": "â³ Application deadline",
    "opportunity_format": "ð§­ Format",
    # Part II: Quick Map Filters
    "geographic_eligibility": "ð Who can apply geographically?",
    "academic_levels": "ð Academic or career level",
    "broad_fields": "ð¬ Broad academic fields",
    "funding_support": "ð° Funding, costs, and support",
    "funding_details": "ð³ Funding and benefits details",
    "audience_groups": "ð Intended, encouraged, or eligible groups",
    "audience_information": "ð«¶ Exact audience or inclusion wording",
    # Part III: Add What You Know
    "application_link": "ðª Direct application link",
    "host_location": "ð Host location",
    "eligible_locations": "ðºï¸ Specific eligible countries or regions",
    "event_dates": "ð Event or program dates",
    "specific_majors": "ð§  Specific majors or specializations",
    "eligibility_details": "ð Other eligibility requirements",
    "application_requirements": "ð¹ Application requirements or selection process",
    "additional_information": "ð Anything else worth knowing?",
    # Final confirmation
    "confirmation": "ð¡ï¸ Adventurer's check",
}

MULTI_VALUE_FIELDS = {
    "geographic_eligibility",
    "academic_levels",
    "broad_fields",
    "funding_support",
    "audience_groups",
    "confirmation",
}

REQUIRED_FIELDS = {
    "opportunity_name",
    "main_category",
    "category",
    "organizer",
    "short_description",
    "official_website",
    "application_deadline",
    "opportunity_format",
}

# ============================================================
# NORMALIZED ROUTING MAPS
# ============================================================

MAIN_CATEGORY_MAP = {
    "events": "events",
    "internships": "internships",
    "competitions": "competitions",
    "research": "research",
    "fellowships": "fellowships",
    "scholarships": "scholarships",
    "courses and training": "courses",
    "innovation and entrepreneurship": "innovation",
    "creative and open calls": "creative-calls",
    "exchanges and mobility": "exchanges",
    "volunteering": "volunteering",
    "other or not sure": "other",
}

CATEGORY_PREFIX_MAP = {
    "events": "events",
    "internships": "internships",
    "competitions": "competitions",
    "research": "research",
    "fellowships": "fellowships",
    "scholarships": "scholarships",
    "courses": "courses",
    "innovation": "innovation",
    "creative": "creative-calls",
    "exchange": "exchanges",
    "volunteering": "volunteering",
}

CATEGORY_MAP = {
    # Events
    "conference": "conference",
    "summit": "summit",
    "forum": "forum",
    "workshop or seminar": "workshop-seminar",
    "networking event": "networking-event",
    "congress": "congress",
    "cultural program": "cultural-program",
    # Internships
    "internship": "internship",
    "apprenticeship": "apprenticeship",
    "traineeship": "traineeship",
    # Competitions
    "competition": "competition",
    "challenge": "challenge",
    "hackathon": "hackathon",
    # Research
    "research program": "research-program",
    "research placement": "research-placement",
    "research internship": "research-internship",
    # Fellowships
    "fellowship": "fellowship",
    "leadership program": "leadership-program",
    # Scholarships
    "scholarship": "scholarship",
    "grant": "grant",
    "travel grant": "travel-grant",
    # Courses and training
    "academy": "academy",
    "summer school": "summer-school",
    "winter school": "winter-school",
    "course or training": "course-training",
    "bootcamp": "bootcamp",
    # Innovation and entrepreneurship
    "startup program": "startup-program",
    "accelerator": "accelerator",
    "incubator": "incubator",
    "entrepreneurship program": "entrepreneurship-program",
    # Creative and open calls
    "creative call": "creative-call",
    "media call": "media-call",
    "writing call": "writing-call",
    "design call": "design-call",
    # Exchanges and mobility
    "exchange program": "exchange-program",
    "mobility program": "mobility-program",
    # Volunteering
    "volunteering program": "volunteering-program",
    "service program": "service-program",
    # Fallback
    "other or not sure": "other",
}

REGION_MAP = {
    "worldwide": "worldwide",
    "africa": "africa",
    "asia": "asia",
    "europe": "europe",
    "european union or eea": "eu-eea",
    "latin america and the caribbean": "latin-america-caribbean",
    "middle east and north africa": "mena",
    "north america": "north-america",
    "oceania": "oceania",
    "host country only": "host-country-only",
    "specific countries": "specific-countries",
    "multiple countries or regions": "multiple-countries-regions",
    "no geographic restriction mentioned": "not-mentioned",
    "not sure": "not-sure",
}

ACADEMIC_LEVEL_MAP = {
    "secondary or high-school students": "high-school",
    "vocational students": "vocational",
    "undergraduate students": "undergraduate",
    "master's students": "masters",
    "doctoral students": "doctoral",
    "postdoctoral researchers": "postdoctoral",
    "recent graduates": "recent-graduates",
    "early-career professionals": "early-career",
    "professionals": "professionals",
    "open to several levels": "multiple-levels",
    "no academic restriction mentioned": "not-mentioned",
    "not sure": "not-sure",
}

BROAD_FIELD_MAP = {
    "engineering and technology": "engineering-technology",
    "computer science and artificial intelligence": "computer-science-ai",
    "mathematics and statistics": "mathematics-statistics",
    "physics and astronomy": "physics-astronomy",
    "chemistry and materials science": "chemistry-materials",
    "biology and life sciences": "biology-life-sciences",
    "medicine and health": "medicine-health",
    "environmental science and sustainability": "environment-sustainability",
    "business and economics": "business-economics",
    "entrepreneurship and innovation": "entrepreneurship-innovation",
    "law and public policy": "law-public-policy",
    "politics and international relations": "politics-international-relations",
    "social sciences": "social-sciences",
    "psychology and behavioural science": "psychology-behavioural-science",
    "education": "education",
    "arts and design": "arts-design",
    "humanities": "humanities",
    "media and communications": "media-communications",
    "architecture and urban planning": "architecture-urban-planning",
    "agriculture and food science": "agriculture-food-science",
    "interdisciplinary": "interdisciplinary",
    "open to all fields": "all-fields",
    "other": "other",
    "not sure": "not-sure",
}

# Community classification comes only from audience_groups.
# audience_information is preserved as supporting text but is never
# examined to infer, add, or remove community tags.
AUDIENCE_MAP = {
    "women": "women",
    "women in stem": "women-in-stem",
    "underrepresented groups in stem": "underrepresented-stem",
    "first-generation or low-income students": "first-generation-low-income",
    "students with disabilities or neurodivergent students": (
        "disability-neurodivergent"
    ),
    "international students": "international-students",
    "refugees, displaced students, or migrant-background students": (
        "refugees-displaced-migrant"
    ),
    "ethnic, racial, or indigenous minorities": (
        "ethnic-racial-indigenous-minorities"
    ),
    "lgbtq+ students": "lgbtq-plus",
    "young researchers": "young-researchers",
    "student founders": "student-founders",
    "rural or remote-community students": "rural-remote-students",
    "another specific community": "other-specific-community",
    "no particular group mentioned": "none-mentioned",
    "not sure": "not-sure",
}

# ============================================================
# BASIC HELPERS
# ============================================================


def fail(message: str) -> None:
    print(f"::error::{message}")
    raise SystemExit(1)


def warn(message: str) -> None:
    print(f"::warning::{message}")


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_value = ascii_value.lower()
    ascii_value = re.sub(r"[^a-z0-9]+", "-", ascii_value)
    return ascii_value.strip("-")


def normalize_compare_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue

        key = cleaned.casefold()
        if key in seen:
            continue

        seen.add(key)
        result.append(cleaned)

    return result


def neutralize_mentions(value: str) -> str:
    """Prevent contributor-controlled text from creating GitHub mentions."""

    return value.replace("@", "@\u200b")


def safe_comment_value(value: Any) -> str:
    if value is None:
        return "Not confirmed"

    text = neutralize_mentions(str(value).strip())
    if not text:
        return "Not confirmed"

    if len(text) > MAX_COMMENT_VALUE_LENGTH:
        return text[:MAX_COMMENT_VALUE_LENGTH] + "â¦"

    return text


def github_request(
    method: str,
    endpoint: str,
    *,
    expected_statuses: tuple[int, ...] = (200,),
    **kwargs: Any,
) -> requests.Response:
    response = requests.request(
        method,
        f"{GITHUB_API}{endpoint}",
        headers=HEADERS,
        timeout=60,
        **kwargs,
    )

    if response.status_code not in expected_statuses:
        fail(
            "GitHub API request failed: "
            f"{method} {endpoint} returned {response.status_code}\n"
            f"{response.text[:1500]}"
        )

    return response


def write_github_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")

    if not output_path:
        print(f"{name}={value}")
        return

    with open(output_path, "a", encoding="utf-8") as output:
        output.write(f"{name}={value}\n")


# ============================================================
# ISSUE READING
# ============================================================


def get_issue() -> dict[str, Any]:
    response = github_request(
        "GET",
        f"/repos/{REPOSITORY}/issues/{ISSUE_NUMBER}",
    )
    issue = response.json()

    if not isinstance(issue, dict):
        fail("GitHub returned an invalid issue response.")

    if issue.get("pull_request"):
        fail("The supplied issue number refers to a pull request.")

    return issue


def split_issue_sections(body: str) -> dict[str, str]:
    """
    GitHub Issue Forms render fields approximately as:

    ### Field label
    Submitted value

    ### Next field
    """

    pattern = re.compile(
        r"^###\s+(.+?)\s*$\n(.*?)(?=^###\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )

    sections: dict[str, str] = {}

    for match in pattern.finditer(body):
        label = match.group(1).strip()
        value = match.group(2).strip()
        sections[label] = value

    return sections


def clean_single_value(value: str) -> str | None:
    cleaned = value.strip()
    empty_values = {
        "",
        "_No response_",
        "No response",
        "None",
    }

    if cleaned in empty_values:
        return None

    # Preserve the raw issue itself exactly on GitHub. Refuse to process
    # extreme individual fields rather than silently modifying the submission.
    if len(cleaned) > MAX_FIELD_LENGTH:
        fail(
            "A submitted field is too large to process safely. "
            f"Maximum field size: {MAX_FIELD_LENGTH} characters."
        )

    return cleaned


def parse_multi_value(value: str) -> list[str]:
    """
    Parse both multi-select dropdowns and checkbox groups.

    GitHub may render checkbox options as ``- [x] value`` and unchecked
    options as ``- [ ] value``. Unchecked values must not enter routing.
    """

    cleaned = clean_single_value(value)
    if cleaned is None:
        return []

    values: list[str] = []

    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Remove a Markdown bullet before checking for checkbox syntax.
        line = re.sub(r"^[-*]\s+", "", line)

        checkbox_match = re.match(r"^\[([xX ])\]\s*(.*)$", line)
        if checkbox_match:
            checked, label = checkbox_match.groups()
            if checked.lower() != "x":
                continue
            line = label.strip()

        if line:
            values.append(line)

    # Some multi-select values may be rendered as one comma-separated line.
    if len(values) == 1 and "," in values[0]:
        values = [
            item.strip()
            for item in values[0].split(",")
            if item.strip()
        ]

    return unique_strings(values)[:MAX_LIST_ITEMS]


def extract_raw_submission(
    issue_body: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    sections = split_issue_sections(issue_body)
    raw_submission: dict[str, Any] = {}

    for internal_name, visible_label in FIELD_LABELS.items():
        raw_value = sections.get(visible_label, "")

        if internal_name in MULTI_VALUE_FIELDS:
            raw_submission[internal_name] = parse_multi_value(raw_value)
        else:
            raw_submission[internal_name] = clean_single_value(raw_value)

    return raw_submission, sections


# ============================================================
# BASIC INTAKE CHECKS
# ============================================================


def check_missing_required_fields(
    raw_submission: dict[str, Any],
) -> list[str]:
    missing: list[str] = []

    for field_name in sorted(REQUIRED_FIELDS):
        value = raw_submission.get(field_name)
        if value is None or value == "" or value == []:
            missing.append(field_name)

    return missing


def looks_like_url(value: Any) -> bool:
    """
    Accept only usable public HTTP or HTTPS URLs.

    This rejects ordinary text, missing schemes, localhost addresses,
    private or loopback IP addresses, embedded credentials, and malformed
    ports.
    """

    if not isinstance(value, str):
        return False

    candidate = value.strip()
    if not candidate or any(character.isspace() for character in candidate):
        return False

    try:
        parsed = urlparse(candidate)
        # Accessing parsed.port also validates malformed ports.
        _ = parsed.port
    except ValueError:
        return False

    if parsed.scheme.lower() not in {"http", "https"}:
        return False

    if not parsed.netloc or not parsed.hostname:
        return False

    # Do not allow credentials inside submitted URLs.
    if parsed.username or parsed.password:
        return False

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return False

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        # Normal public domain names should contain at least one dot.
        if "." not in hostname:
            return False
    else:
        # Reject localhost, private, reserved, and link-local IP addresses.
        if not address.is_global:
            return False

    return True


def parse_category_choice(value: Any) -> tuple[str | None, str]:
    """
    Convert a value such as ``Events â Conference`` into:

        ("events", "conference")

    The first result is the broad category implied by the specific dropdown.
    It is used for consistency checking. ``Other or Not Sure`` has no implied
    broad category.
    """

    if not isinstance(value, str):
        return None, "other"

    cleaned = value.strip()
    if not cleaned:
        return None, "other"

    normalized = normalize_compare_text(cleaned)
    if normalized == "other or not sure":
        return None, "other"

    parts = re.split(r"\s+[ââ-]\s+", cleaned, maxsplit=1)

    if len(parts) != 2:
        return (
            None,
            CATEGORY_MAP.get(
                normalized,
                slugify(cleaned) or "other",
            ),
        )

    prefix, subtype = parts
    expected_main_category = CATEGORY_PREFIX_MAP.get(
        normalize_compare_text(prefix)
    )

    normalized_subtype = normalize_compare_text(subtype)
    specific_category = CATEGORY_MAP.get(
        normalized_subtype,
        slugify(subtype) or "other",
    )

    return expected_main_category, specific_category


def normalized_main_category(value: Any) -> str:
    raw_value = str(value or "")
    return MAIN_CATEGORY_MAP.get(
        normalize_compare_text(raw_value),
        slugify(raw_value) or "other",
    )


def basic_intake_warnings(
    raw_submission: dict[str, Any],
) -> list[str]:
    warnings: list[str] = []

    official_website = raw_submission.get("official_website")
    application_link = raw_submission.get("application_link")

    if official_website and not looks_like_url(official_website):
        warnings.append(
            "The official source does not appear to be a complete "
            "HTTP or HTTPS URL."
        )

    if application_link and not looks_like_url(application_link):
        warnings.append(
            "The application link does not appear to be a complete "
            "HTTP or HTTPS URL."
        )

    selected_main_category = normalized_main_category(
        raw_submission.get("main_category")
    )
    expected_main_category, _ = parse_category_choice(
        raw_submission.get("category")
    )

    if (
        expected_main_category is not None
        and expected_main_category != selected_main_category
    ):
        warnings.append(
            "The selected main category does not match the specific "
            "opportunity type. "
            f"Main category: '{raw_submission.get('main_category')}'. "
            f"Specific type implies: '{expected_main_category}'."
        )

    # Deliberately do not inspect audience_information here. Community
    # categories come only from the audience_groups dropdown.
    return warnings


# ============================================================
# ROUTING HINTS
# ============================================================


def mapped_values(
    values: list[str],
    mapping: dict[str, str],
) -> list[str]:
    results: list[str] = []

    for value in values:
        key = normalize_compare_text(value)
        mapped = mapping.get(key)

        if mapped:
            results.append(mapped)
            continue

        fallback = slugify(value)
        if fallback:
            results.append(fallback)

    return unique_strings(results)


def extract_specific_major_hints(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []

    parts = re.split(r"[\n,;â¢]+", value)
    results = [slugify(part) for part in parts if slugify(part)]
    return unique_strings(results)[:MAX_LIST_ITEMS]


def extract_keyword_hints(
    raw_submission: dict[str, Any],
) -> list[str]:
    # audience_information is intentionally excluded. It must not affect
    # community classification or routing tags.
    source_fields = [
        "opportunity_name",
        "short_description",
        "specific_majors",
        "eligibility_details",
        "funding_details",
        "additional_information",
    ]

    words: list[str] = []

    for field_name in source_fields:
        value = raw_submission.get(field_name)
        if not isinstance(value, str):
            continue

        routing_text = value[:MAX_FIELD_LENGTH]
        tokens = re.findall(
            r"[A-Za-zÃ-Ã¿0-9+#.-]{3,}",
            routing_text.lower(),
        )
        words.extend(tokens)

    stop_words = {
        "this",
        "that",
        "with",
        "from",
        "have",
        "will",
        "into",
        "your",
        "their",
        "they",
        "them",
        "students",
        "student",
        "opportunity",
        "program",
        "programme",
        "application",
        "applicants",
        "participants",
        "include",
        "includes",
        "including",
        "other",
        "more",
        "about",
        "under",
        "over",
        "where",
        "which",
        "when",
        "what",
        "and",
        "the",
        "for",
        "are",
        "not",
    }

    filtered = [slugify(word) for word in words if word not in stop_words]
    return unique_strings([item for item in filtered if item])[
        :MAX_ROUTING_KEYWORDS
    ]


def build_routing_hints(
    raw_submission: dict[str, Any],
) -> dict[str, Any]:
    main_category = normalized_main_category(
        raw_submission.get("main_category")
    )

    expected_main_category, category = parse_category_choice(
        raw_submission.get("category")
    )

    category_pair_matches = (
        expected_main_category is None
        or expected_main_category == main_category
    )

    return {
        "main_category": main_category,
        "category": category,
        "category_group_from_specific": expected_main_category,
        "category_pair_matches": category_pair_matches,
        "regions": mapped_values(
            raw_submission.get("geographic_eligibility", []),
            REGION_MAP,
        ),
        "academic_levels": mapped_values(
            raw_submission.get("academic_levels", []),
            ACADEMIC_LEVEL_MAP,
        ),
        "broad_fields": mapped_values(
            raw_submission.get("broad_fields", []),
            BROAD_FIELD_MAP,
        ),
        "specific_majors": extract_specific_major_hints(
            raw_submission.get("specific_majors")
        ),
        "audiences": mapped_values(
            raw_submission.get("audience_groups", []),
            AUDIENCE_MAP,
        ),
        "keywords": extract_keyword_hints(raw_submission),
    }


# ============================================================
# MODERATOR ROUTING
# ============================================================


def load_moderator_configuration() -> dict[str, Any]:
    if not MODERATOR_FILE.exists():
        warn(
            f"Moderator registry not found at {MODERATOR_FILE}. "
            "No automatic specialist routing will occur."
        )
        return {}

    try:
        data = yaml.safe_load(MODERATOR_FILE.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        fail(f"Invalid YAML in {MODERATOR_FILE}: {exc}")

    if data is None:
        return {}

    if not isinstance(data, dict):
        fail(f"Expected an object in {MODERATOR_FILE}.")

    return data


def moderator_matches(
    configured_values: Any,
    submitted_values: list[str],
) -> int:
    if not isinstance(configured_values, list):
        return 0

    # Wildcards represent fallback/general administrators. They should not
    # outscore topic specialists.
    if "*" in configured_values:
        return 0

    normalized_configured = {
        slugify(str(item))
        for item in configured_values
        if str(item).strip()
    }
    normalized_submitted = {
        slugify(str(item))
        for item in submitted_values
        if str(item).strip()
    }

    return len(normalized_configured & normalized_submitted)


def score_moderator(
    moderator: dict[str, Any],
    routing_hints: dict[str, Any],
    weights: dict[str, int],
) -> int:
    specialties = moderator.get("specialties", {})
    if not isinstance(specialties, dict):
        return 0

    category_values = unique_strings(
        [
            routing_hints["main_category"],
            routing_hints["category"],
        ]
    )

    score = 0
    score += moderator_matches(
        specialties.get("categories"),
        category_values,
    ) * weights.get("category", 6)

    configured_fields = (
        specialties.get("academic_fields")
        or specialties.get("broad_fields")
        or []
    )
    submitted_fields = unique_strings(
        routing_hints["broad_fields"]
        + routing_hints["specific_majors"]
    )
    score += moderator_matches(
        configured_fields,
        submitted_fields,
    ) * weights.get("academic_field", 5)

    score += moderator_matches(
        specialties.get("audiences"),
        routing_hints["audiences"],
    ) * weights.get("audience", 5)

    score += moderator_matches(
        specialties.get("regions"),
        routing_hints["regions"],
    ) * weights.get("region", 2)

    score += moderator_matches(
        specialties.get("countries"),
        routing_hints.get("host_location_keywords", []),
    ) * weights.get("country", 4)

    score += moderator_matches(
        specialties.get("keywords"),
        routing_hints["keywords"],
    ) * weights.get("keyword", 1)

    return score


def get_open_assignment_count(username: str) -> int:
    query = (
        f"repo:{REPOSITORY} "
        f"is:issue "
        f"is:open "
        f"assignee:{username} "
        f"label:needs-review"
    )

    response = requests.get(
        f"{GITHUB_API}/search/issues",
        headers=HEADERS,
        params={"q": query, "per_page": 1},
        timeout=30,
    )

    if response.status_code != 200:
        warn(
            f"Could not check workload for {username}: "
            f"{response.status_code}"
        )
        return 0

    data = response.json()
    try:
        return int(data.get("total_count", 0))
    except (TypeError, ValueError):
        return 0


def choose_moderators(
    moderator_config: dict[str, Any],
    routing_hints: dict[str, Any],
) -> list[str]:
    moderators = moderator_config.get("moderators", {})
    if not isinstance(moderators, dict):
        moderators = {}

    governance = moderator_config.get("governance", {})
    if not isinstance(governance, dict):
        governance = {}

    routing = moderator_config.get("routing", {})
    if not isinstance(routing, dict):
        routing = {}

    fallback_reviewers = governance.get("fallback_reviewers", [])
    if not isinstance(fallback_reviewers, list):
        fallback_reviewers = []

    try:
        max_assignees = max(
            1,
            min(int(routing.get("max_issue_assignees", 2)), 10),
        )
    except (TypeError, ValueError):
        max_assignees = 2

    weights = routing.get("score_weights", {})
    if not isinstance(weights, dict):
        weights = {}

    scored: list[tuple[int, int, str]] = []

    for username, moderator in moderators.items():
        if not isinstance(moderator, dict):
            continue

        if moderator.get("active", True) is not True:
            continue

        roles = moderator.get("roles", [])
        if (
            isinstance(roles, list)
            and "moderator" not in roles
            and "administrator" not in roles
            and "final-approver" not in roles
        ):
            continue

        score = score_moderator(moderator, routing_hints, weights)
        workload = get_open_assignment_count(username)

        workload_config = moderator.get("workload", {})
        maximum = None
        if isinstance(workload_config, dict):
            maximum = workload_config.get("max_open_reviews")

        try:
            if maximum is not None and workload >= int(maximum):
                continue
        except (TypeError, ValueError):
            pass

        if score > 0:
            scored.append((score, -workload, username))

    scored.sort(reverse=True)
    selected = [
        username
        for _, _, username in scored[:max_assignees]
    ]

    # General administrators are only used when no specialist matched.
    if not selected:
        selected = [
            str(username)
            for username in fallback_reviewers
            if str(username).strip()
        ][:max_assignees]

    return unique_strings(selected)


# ============================================================
# LABELS AND ASSIGNEES
# ============================================================


def ensure_label(
    name: str,
    color: str,
    description: str,
) -> None:
    encoded_name = quote(name, safe="")
    response = requests.get(
        f"{GITHUB_API}/repos/{REPOSITORY}/labels/{encoded_name}",
        headers=HEADERS,
        timeout=30,
    )

    if response.status_code == 200:
        return

    if response.status_code != 404:
        fail(
            f"Could not check label '{name}': "
            f"{response.status_code} {response.text[:500]}"
        )

    github_request(
        "POST",
        f"/repos/{REPOSITORY}/labels",
        expected_statuses=(201,),
        json={
            "name": name,
            "color": color,
            "description": description,
        },
    )


def add_labels(labels: list[str]) -> None:
    if not labels:
        return

    github_request(
        "POST",
        f"/repos/{REPOSITORY}/issues/{ISSUE_NUMBER}/labels",
        expected_statuses=(200,),
        json={"labels": unique_strings(labels)},
    )


def assign_moderators(usernames: list[str]) -> list[str]:
    if not usernames:
        return []

    response = requests.post(
        f"{GITHUB_API}/repos/{REPOSITORY}/issues/{ISSUE_NUMBER}/assignees",
        headers=HEADERS,
        json={"assignees": usernames},
        timeout=30,
    )

    if response.status_code == 201:
        data = response.json()
        assigned = data.get("assignees", [])
        return [
            item["login"]
            for item in assigned
            if isinstance(item, dict)
            and isinstance(item.get("login"), str)
        ]

    if response.status_code == 422:
        warn(
            "One or more configured moderators could not be assigned. "
            "Confirm that they are repository collaborators."
        )
        return []

    fail(
        "Could not assign moderators: "
        f"{response.status_code} {response.text[:1000]}"
    )
    return []


# ============================================================
# DUPLICATE-SAFE INTAKE COMMENT
# ============================================================


def intake_comment_exists() -> bool:
    response = github_request(
        "GET",
        f"/repos/{REPOSITORY}/issues/{ISSUE_NUMBER}/comments",
    )
    comments = response.json()

    if not isinstance(comments, list):
        return False

    return any(
        INTAKE_COMMENT_MARKER in str(comment.get("body", ""))
        for comment in comments
        if isinstance(comment, dict)
    )


def post_intake_comment(
    raw_submission: dict[str, Any],
    assigned_moderators: list[str],
    missing_fields: list[str],
    warnings: list[str],
) -> None:
    if intake_comment_exists():
        print("Intake comment already exists. Skipping duplicate.")
        return

    title = safe_comment_value(raw_submission.get("opportunity_name"))
    main_category = safe_comment_value(
        raw_submission.get("main_category")
    )
    category = safe_comment_value(raw_submission.get("category"))
    deadline = safe_comment_value(
        raw_submission.get("application_deadline")
    )

    moderator_text = (
        ", ".join(f"@{username}" for username in assigned_moderators)
        if assigned_moderators
        else "Awaiting moderator assignment"
    )

    lines = [
        INTAKE_COMMENT_MARKER,
        "## OFFMAP Has Logged This Discovery",
        "",
        f"**Opportunity:** {title}",
        f"**Main category:** {main_category}",
        f"**Specific type:** {category}",
        f"**Submitted deadline:** {deadline}",
        f"**Assigned moderator:** {moderator_text}",
        "",
        "The original issue has been preserved as the raw submission record.",
    ]

    if missing_fields or warnings:
        lines.extend(["", "### Initial Intake Notes"])

    for field_name in missing_fields:
        lines.append(f"- Missing required field: `{field_name}`")

    for warning_message in warnings:
        lines.append(f"- {neutralize_mentions(warning_message)}")

    lines.extend(
        [
            "",
            "> This is only the intake stage. Official-source research "
            "and human review still follow.",
        ]
    )

    github_request(
        "POST",
        f"/repos/{REPOSITORY}/issues/{ISSUE_NUMBER}/comments",
        expected_statuses=(201,),
        json={"body": "\n".join(lines)},
    )


# ============================================================
# RAW COPY CREATION
# ============================================================


def find_unmatched_sections(
    all_sections: dict[str, str],
) -> dict[str, str]:
    recognized_labels = set(FIELD_LABELS.values())
    return {
        label: value
        for label, value in all_sections.items()
        if label not in recognized_labels
    }


def build_raw_record(
    issue: dict[str, Any],
    raw_submission: dict[str, Any],
    unmatched_sections: dict[str, str],
    routing_hints: dict[str, Any],
    assigned_moderators: list[str],
    missing_fields: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    user = issue.get("user", {})
    author = user.get("login") if isinstance(user, dict) else None

    return {
        "schema_version": 2,
        "record_type": "raw-submission",
        "preservation_policy": {
            "original_issue_is_source_of_truth": True,
            "raw_values_may_be_overwritten": False,
            "ai_research_must_create_separate_copy": True,
        },
        "repository": REPOSITORY,
        "issue": {
            "number": ISSUE_NUMBER,
            "title": issue.get("title"),
            "url": issue.get("html_url"),
            "api_url": issue.get("url"),
            "author": author,
            "created_at": issue.get("created_at"),
            "updated_at": issue.get("updated_at"),
            "state": issue.get("state"),
            "raw_body": issue.get("body") or "",
        },
        "raw_submission": raw_submission,
        "unmatched_form_sections": unmatched_sections,
        "routing_hints": routing_hints,
        "moderation": {
            "assigned_moderators": assigned_moderators,
            "missing_required_fields": missing_fields,
            "initial_warnings": warnings,
            "human_review_required": True,
        },
        "processing": {
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "parser": "scripts/process_submission.py",
            "parser_schema_version": 2,
            "research_completed": False,
            "ai_publication_copy_created": False,
            "published": False,
        },
    }


def save_raw_record(record: dict[str, Any]) -> Path:
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIRECTORY / f"raw-submission-{ISSUE_NUMBER}.json"
    output_file.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_file


# ============================================================
# MAIN
# ============================================================


def main() -> None:
    issue = get_issue()
    issue_body = issue.get("body") or ""

    if len(issue_body) > MAX_ISSUE_BODY_LENGTH:
        fail(
            "The submitted issue is too large to process safely. "
            f"Maximum issue-body size: {MAX_ISSUE_BODY_LENGTH} characters."
        )

    raw_submission, all_sections = extract_raw_submission(issue_body)
    missing_fields = check_missing_required_fields(raw_submission)
    warnings = basic_intake_warnings(raw_submission)
    unmatched_sections = find_unmatched_sections(all_sections)

    official_source_valid = looks_like_url(
        raw_submission.get("official_website")
    )
    safe_to_research = not missing_fields and official_source_valid

    routing_hints = build_routing_hints(raw_submission)

    host_location = raw_submission.get("host_location")
    routing_hints["host_location_keywords"] = (
        unique_strings(
            [
                slugify(item)
                for item in re.split(r"[\n,;]+", host_location)
                if slugify(item)
            ]
        )[:MAX_LIST_ITEMS]
        if isinstance(host_location, str)
        else []
    )

    moderator_config = load_moderator_configuration()
    selected_moderators = choose_moderators(
        moderator_config,
        routing_hints,
    )
    assigned_moderators = assign_moderators(selected_moderators)

    main_category_slug = routing_hints["main_category"]
    category_slug = routing_hints["category"]

    ensure_label(
        "new-discovery",
        "8B5CF6",
        "A newly submitted opportunity.",
    )
    ensure_label(
        "needs-review",
        "F4C542",
        "Requires human verification before publication.",
    )
    ensure_label(
        "intake-parsed",
        "1D76DB",
        "The issue form was parsed into a preserved raw record.",
    )

    main_category_label = f"type: {main_category_slug}"
    category_label = f"category: {category_slug}"

    ensure_label(
        main_category_label,
        "BFD4F2",
        f"Broad opportunity type: {main_category_slug}.",
    )
    ensure_label(
        category_label,
        "D8B4FE",
        f"Specific opportunity category: {category_slug}.",
    )

    labels_to_add = [
        "new-discovery",
        "needs-review",
        "intake-parsed",
        main_category_label,
        category_label,
    ]

    if missing_fields:
        ensure_label(
            "missing-information",
            "D73A4A",
            "Important submission information is missing.",
        )
        labels_to_add.append("missing-information")

    if not official_source_valid:
        ensure_label(
            "invalid-source-url",
            "B60205",
            "The submitted official source is not a valid public URL.",
        )
        labels_to_add.append("invalid-source-url")

    if not routing_hints["category_pair_matches"]:
        ensure_label(
            "category-mismatch",
            "E99695",
            "The broad and specific opportunity categories do not match.",
        )
        labels_to_add.append("category-mismatch")

    add_labels(labels_to_add)

    raw_record = build_raw_record(
        issue=issue,
        raw_submission=raw_submission,
        unmatched_sections=unmatched_sections,
        routing_hints=routing_hints,
        assigned_moderators=assigned_moderators,
        missing_fields=missing_fields,
        warnings=warnings,
    )
    output_file = save_raw_record(raw_record)

    post_intake_comment(
        raw_submission=raw_submission,
        assigned_moderators=assigned_moderators,
        missing_fields=missing_fields,
        warnings=warnings,
    )

    write_github_output("submission_file", str(output_file))
    write_github_output("raw_submission_file", str(output_file))
    write_github_output("main_category", main_category_slug)
    write_github_output("category", category_slug)
    write_github_output(
        "moderators",
        json.dumps(assigned_moderators, ensure_ascii=False),
    )
    write_github_output(
        "missing_fields",
        json.dumps(missing_fields, ensure_ascii=False),
    )
    write_github_output(
        "safe_to_research",
        "true" if safe_to_research else "false",
    )

    print("Raw submission preserved successfully.")
    print(f"Raw record path: {output_file}")
    print(f"Main category routing hint: {main_category_slug}")
    print(f"Specific category routing hint: {category_slug}")
    print(
        "Assigned moderators: "
        + (
            ", ".join(assigned_moderators)
            if assigned_moderators
            else "none"
        )
    )


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as exc:
        fail(f"Network request failed: {exc}")
    except KeyboardInterrupt:
        sys.exit(130)
