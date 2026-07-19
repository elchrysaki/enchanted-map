from __future__ import annotations

import re
from pathlib import Path

from opportunity_document import (
    OpportunityDocumentError,
    parse_opportunity_document,
)


ROOT = Path(__file__).resolve().parents[1]
README_FILE = ROOT / "README.md"
OPPORTUNITIES_DIR = ROOT / "opportunities"

VERIFIED_STATUSES = {
    "published",
    "archived",
}

ACTIVE_STATUS = "published"

VERIFIED_DESTINATION = "opportunities/README.md"
ACTIVE_DESTINATION = "opportunities/README.md"


def count_opportunities() -> tuple[int, int]:
    verified = 0
    active = 0

    for path in sorted(
        OPPORTUNITIES_DIR.rglob("*.md")
    ):
        if path.name == "README.md":
            continue

        try:
            metadata, _ = parse_opportunity_document(
                path.read_text(encoding="utf-8")
            )
        except OpportunityDocumentError as error:
            print(
                f"Skipping unsupported opportunity file "
                f"{path}: {error}"
            )
            continue

        status = str(
            metadata.get("status", "")
        ).strip().casefold()

        if status in VERIFIED_STATUSES:
            verified += 1

        if status == ACTIVE_STATUS:
            active += 1

    return verified, active


def badge(
    *,
    label: str,
    value: int,
    colour: str,
    destination: str,
) -> str:
    image = (
        "https://img.shields.io/badge/"
        f"{label}-{value}-{colour}"
        "?style=for-the-badge"
    )

    return (
        f"[![{label.title()}]({image})]"
        f"({destination})"
    )


def replace_badge(
    readme: str,
    *,
    label_pattern: str,
    replacement: str,
) -> str:
    pattern = re.compile(
        rf"\[!\[[^\]]*{label_pattern}[^\]]*\]"
        rf"\([^)]+\)\]"
        rf"\([^)]+\)",
        flags=re.IGNORECASE,
    )

    updated, count = pattern.subn(
        replacement,
        readme,
        count=1,
    )

    if count != 1:
        raise SystemExit(
            f"Could not find exactly one "
            f"{label_pattern} badge in README.md."
        )

    return updated


def main() -> None:
    verified, active = count_opportunities()

    readme = README_FILE.read_text(
        encoding="utf-8"
    )

    readme = replace_badge(
        readme,
        label_pattern="(?:Opportunities|Verified)",
        replacement=badge(
            label="Verified",
            value=verified,
            colour="blueviolet",
            destination=VERIFIED_DESTINATION,
        ),
    )

    readme = replace_badge(
        readme,
        label_pattern="Closing Soon",
        replacement=badge(
            label="Active",
            value=active,
            colour="orange",
            destination=ACTIVE_DESTINATION,
        ),
    )

    README_FILE.write_text(
        readme,
        encoding="utf-8",
        newline="\n",
    )

    print(f"Verified opportunities: {verified}")
    print(f"Active opportunities: {active}")


if __name__ == "__main__":
    main()
