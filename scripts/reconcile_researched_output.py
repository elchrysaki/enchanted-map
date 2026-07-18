from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


ISSUE_NUMBER = int(os.environ["ISSUE_NUMBER"])
RESEARCHED_SUBMISSION_FILE = Path(
    os.environ.get(
        "RESEARCHED_SUBMISSION_FILE",
        f"artifacts/researched-submission-{ISSUE_NUMBER}.json",
    )
)

SPECIFIC_CATEGORY_PARENT = {
    "conference": "events",
    "summit": "events",
    "forum": "events",
    "workshop-seminar": "events",
    "networking-event": "events",
    "congress": "events",
    "cultural-program": "events",
    "internship": "internships",
    "apprenticeship": "internships",
    "traineeship": "internships",
    "competition": "competitions",
    "challenge": "competitions",
    "hackathon": "competitions",
    "research-program": "research",
    "research-placement": "research",
    "research-internship": "research",
    "fellowship": "fellowships",
    "leadership-program": "fellowships",
    "scholarship": "scholarships",
    "grant": "scholarships",
    "travel-grant": "scholarships",
    "academy": "courses",
    "summer-school": "courses",
    "winter-school": "courses",
    "course-training": "courses",
    "bootcamp": "courses",
    "startup-program": "innovation",
    "accelerator": "innovation",
    "incubator": "innovation",
    "entrepreneurship-program": "innovation",
    "creative-call": "creative-calls",
    "media-call": "creative-calls",
    "writing-call": "creative-calls",
    "design-call": "creative-calls",
    "exchange-program": "exchanges",
    "mobility-program": "exchanges",
    "volunteering-program": "volunteering",
    "service-program": "volunteering",
}


def write_output(name: str, value: str) -> None:
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
        raise ValueError(f"'{key}' must be an object.")
    return value


def append_unique(
    parent: dict[str, Any],
    key: str,
    message: str,
) -> None:
    value = parent.get(key)
    if not isinstance(value, list):
        value = []
        parent[key] = value
    if message not in value:
        value.append(message)


def reconcile(record: dict[str, Any]) -> bool:
    identity = require_object(record, "identity")
    main_field = require_object(identity, "main_category")
    category_field = require_object(identity, "category")

    specific = category_field.get("researched")
    if not isinstance(specific, str):
        return False

    specific = specific.strip()
    expected_main = SPECIFIC_CATEGORY_PARENT.get(specific)
    if expected_main is None:
        return False

    current_main = main_field.get("researched")
    if current_main == expected_main:
        return False

    main_field["researched"] = expected_main
    main_field["status"] = "possible-conflict"

    category_evidence = category_field.get("evidence")
    main_evidence = main_field.get("evidence")
    if (
        isinstance(category_evidence, list)
        and category_evidence
        and (
            not isinstance(main_evidence, list)
            or not main_evidence
        )
    ):
        main_field["evidence"] = list(category_evidence)

    summary = require_object(record, "research_summary")

    previous_main = (
        current_main
        if isinstance(current_main, str) and current_main.strip()
        else "missing"
    )
    conflict_note = (
        f"The researched specific category '{specific}' belongs under "
        f"'{expected_main}', not '{previous_main}'. OffMap normalized the "
        "researched pair together while preserving the contributor's "
        "original values under raw."
    )
    append_unique(
        summary,
        "possible_conflicts",
        conflict_note,
    )
    append_unique(
        summary,
        "moderator_focus",
        "Confirm the officially researched main and specific category pair.",
    )

    return True


def main() -> None:
    if not RESEARCHED_SUBMISSION_FILE.exists():
        raise SystemExit(
            f"Researched submission file not found: "
            f"{RESEARCHED_SUBMISSION_FILE}"
        )

    try:
        record = json.loads(
            RESEARCHED_SUBMISSION_FILE.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"Invalid researched-submission JSON: {exc}"
        ) from exc

    if not isinstance(record, dict):
        raise SystemExit(
            "Researched submission must be a JSON object."
        )

    changed = reconcile(record)

    temporary = RESEARCHED_SUBMISSION_FILE.with_suffix(
        RESEARCHED_SUBMISSION_FILE.suffix + ".tmp"
    )
    temporary.write_text(
        json.dumps(
            record,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(RESEARCHED_SUBMISSION_FILE)

    identity = record.get("identity", {})
    main_category = (
        identity.get("main_category", {}).get("researched", "other")
        if isinstance(identity, dict)
        else "other"
    )
    category = (
        identity.get("category", {}).get("researched", "other")
        if isinstance(identity, dict)
        else "other"
    )

    write_output(
        "researched_submission_file",
        str(RESEARCHED_SUBMISSION_FILE),
    )
    write_output(
        "reconciled_main_category",
        str(main_category),
    )
    write_output(
        "reconciled_category",
        str(category),
    )
    write_output(
        "category_pair_changed",
        "true" if changed else "false",
    )

    if changed:
        print(
            "Researched category pair was reconciled for human review."
        )
    else:
        print("Researched category pair already matched.")


if __name__ == "__main__":
    main()
