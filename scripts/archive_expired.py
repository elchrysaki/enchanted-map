#!/usr/bin/env python3
"""Archive published OffMap opportunities whose application deadline has passed."""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from opportunity_document import (  # noqa: E402
    OpportunityDocumentError,
    parse_opportunity_document,
    render_opportunity_document,
)

OPPORTUNITIES_DIR = ROOT / "opportunities"
ARCHIVE_DIR = OPPORTUNITIES_DIR / "archive"
ARCHIVE_PAGE = ROOT / "ARCHIVE.md"


def clean(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if not isinstance(value, str):
        return None
    result = " ".join(value.split())
    return result or None


def nested(record: dict[str, Any], *keys: str) -> Any:
    value: Any = record
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def parse_iso_date(value: Any) -> date | None:
    text = clean(value)
    if text is None:
        return None
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == text else None


def is_rolling(record: dict[str, Any]) -> bool:
    candidates = (
        nested(record, "dates", "application_deadline", "raw"),
        nested(record, "dates", "application_deadline", "display"),
    )
    return any(
        "rolling" in text.casefold()
        for value in candidates
        if (text := clean(value)) is not None
    )


def markdown_text(value: Any, fallback: str = "Not confirmed") -> str:
    text = clean(value) or fallback
    return (
        text.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("\n", " ")
    )


def load_archived_records() -> list[tuple[Path, dict[str, Any]]]:
    records: list[tuple[Path, dict[str, Any]]] = []
    if not ARCHIVE_DIR.exists():
        return records

    for path in sorted(ARCHIVE_DIR.rglob("*.md")):
        if path.name.casefold() == "readme.md":
            continue
        try:
            metadata, _ = parse_opportunity_document(path.read_text(encoding="utf-8"))
        except (OSError, OpportunityDocumentError) as exc:
            raise SystemExit(
                f"::error::Could not read archived opportunity {path}: {exc}"
            ) from exc
        if clean(metadata.get("status")) == "archived":
            records.append((path, metadata))

    def sort_key(item: tuple[Path, dict[str, Any]]) -> tuple[str, str]:
        _path, metadata = item
        deadline = clean(
            nested(metadata, "dates", "application_deadline", "normalized")
        ) or "0000-00-00"
        title = clean(metadata.get("title")) or ""
        return deadline, title.casefold()

    records.sort(key=sort_key, reverse=True)
    return records


def write_archive_page() -> None:
    records = load_archived_records()
    lines = [
        "# 🗃️ Past OffMap Opportunities",
        "",
        (
            "These opportunities are kept for reference after their application "
            "deadlines pass. Check the official organizer before relying on an "
            "older listing or waiting for a future cycle."
        ),
        "",
    ]

    if not records:
        lines.extend(["> No opportunities have been archived yet.", ""])
    else:
        lines.extend(
            [
                "| Opportunity | Category | Deadline | Archived reason |",
                "|---|---|---|---|",
            ]
        )
        for path, metadata in records:
            title = markdown_text(metadata.get("title"), "Untitled opportunity")
            category = markdown_text(metadata.get("main_category"))
            deadline = markdown_text(
                nested(metadata, "dates", "application_deadline", "display")
                or nested(metadata, "dates", "application_deadline", "normalized")
                or nested(metadata, "dates", "application_deadline", "raw")
            )
            relative = path.relative_to(ROOT).as_posix()
            lines.append(
                f"| [{title}](<{relative}>) | {category} | {deadline} | "
                "Application deadline passed |"
            )
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            (
                "_Generated automatically by `scripts/archive_expired.py`. "
                "Archived listings remain verified history but are not counted "
                "as active opportunities._"
            ),
            "",
        ]
    )
    ARCHIVE_PAGE.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def archive_expired(*, today: date) -> list[tuple[Path, Path]]:
    moved: list[tuple[Path, Path]] = []
    OPPORTUNITIES_DIR.mkdir(parents=True, exist_ok=True)

    for path in sorted(OPPORTUNITIES_DIR.rglob("*.md")):
        if path.name.casefold() == "readme.md":
            continue
        relative = path.relative_to(OPPORTUNITIES_DIR)
        if relative.parts and relative.parts[0] == "archive":
            continue

        try:
            metadata, body = parse_opportunity_document(path.read_text(encoding="utf-8"))
        except (OSError, OpportunityDocumentError) as exc:
            raise SystemExit(f"::error::Could not read opportunity {path}: {exc}") from exc

        if clean(metadata.get("status")) != "published" or is_rolling(metadata):
            continue

        deadline = parse_iso_date(
            nested(metadata, "dates", "application_deadline", "normalized")
        )
        if deadline is None or deadline >= today:
            continue

        main_category = clean(metadata.get("main_category"))
        slug = clean(metadata.get("slug"))
        if not main_category or "/" in main_category or main_category in {".", ".."}:
            raise SystemExit(f"::error::{path}: unsafe or missing main_category.")
        if not slug or "/" in slug or slug in {".", ".."}:
            raise SystemExit(f"::error::{path}: unsafe or missing slug.")
        if slug != path.stem:
            raise SystemExit(f"::error::{path}: slug does not match the filename.")

        destination = ARCHIVE_DIR / main_category / f"{slug}.md"
        if destination.exists():
            raise SystemExit(
                f"::error::Archive destination already exists: {destination}"
            )

        archived_at = datetime.now(timezone.utc).isoformat()
        metadata["status"] = "archived"
        archival = metadata.get("archival")
        if archival is None:
            archival = {}
            metadata["archival"] = archival
        if not isinstance(archival, dict):
            raise SystemExit(f"::error::{path}: archival metadata must be an object.")
        archival.update(
            {
                "archived_at": archived_at,
                "reason": "application-deadline-passed",
                "application_deadline": deadline.isoformat(),
                "previous_status": "published",
            }
        )

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            render_opportunity_document(metadata, body),
            encoding="utf-8",
            newline="\n",
        )
        path.unlink()
        moved.append((path, destination))

    return moved


def main() -> None:
    today = datetime.now(timezone.utc).date()
    moved = archive_expired(today=today)
    write_archive_page()

    for source, destination in moved:
        print(
            "Archived expired opportunity: "
            f"{source.relative_to(ROOT)} -> {destination.relative_to(ROOT)}"
        )
    print(f"Archived this run: {len(moved)}")
    print(f"Archive page: {ARCHIVE_PAGE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
