from __future__ import annotations

import re
from typing import Any

import yaml


HIDDEN_METADATA = re.compile(
    r"\A<!--\s*OFFMAP-METADATA\s*\n"
    r"(.*?)\nOFFMAP-METADATA-END\s*-->\s*"
    r"(?:\n|$)(.*)\Z",
    re.DOTALL,
)

LEGACY_FRONT_MATTER = re.compile(
    r"\A---\s*\n(.*?)\n---\s*(?:\n|$)(.*)\Z",
    re.DOTALL,
)


class OpportunityDocumentError(ValueError):
    pass


def parse_opportunity_document(
    text: str,
) -> tuple[dict[str, Any], str]:
    """Read hidden OffMap metadata or legacy YAML front matter."""

    match = HIDDEN_METADATA.match(text)
    if match is None:
        match = LEGACY_FRONT_MATTER.match(text)

    if match is None:
        raise OpportunityDocumentError(
            "Opportunity file has neither hidden OffMap metadata nor "
            "legacy YAML front matter."
        )

    try:
        metadata = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise OpportunityDocumentError(
            f"Opportunity metadata is invalid YAML: {exc}"
        ) from exc

    if not isinstance(metadata, dict):
        raise OpportunityDocumentError(
            "Opportunity metadata must be a YAML object."
        )

    return metadata, match.group(2).lstrip("\n")


def dump_metadata(metadata: dict[str, Any]) -> str:
    return yaml.safe_dump(
        metadata,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=1000,
    ).strip()



def _clean_url(value: Any) -> str:
    if not isinstance(value, str):
        return ""

    return value.strip()


def _insert_contextual_link(
    body: str,
    heading_pattern: str,
    marker: str,
    link_markdown: str,
) -> str:
    """Insert one link at the end of a Markdown section."""

    if not link_markdown or marker in body:
        return body

    heading = re.search(
        heading_pattern,
        body,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    if heading is None:
        return body

    remaining = body[heading.end():]

    next_heading = re.search(
        r"^##\s+",
        remaining,
        flags=re.MULTILINE,
    )

    if next_heading is None:
        insertion_point = len(body)
    else:
        insertion_point = heading.end() + next_heading.start()

    before = body[:insertion_point].rstrip()
    after = body[insertion_point:].lstrip("\n")

    if after:
        return (
            f"{before}\n\n"
            f"{link_markdown}\n\n"
            f"{after}"
        )

    return f"{before}\n\n{link_markdown}\n"


def _add_contextual_links(
    metadata: dict[str, Any],
    body: str,
) -> str:
    application = metadata.get("application")

    if not isinstance(application, dict):
        return body

    official_url = _clean_url(
        application.get("official_page")
    )
    application_url = _clean_url(
        application.get("application_page")
    )

    updated = body

    if official_url:
        updated = _insert_contextual_link(
            updated,
            (
                r"^##[^\n]*"
                r"Why this opportunity is worth your attention"
                r"[^\n]*$"
            ),
            "Visit the official opportunity website",
            (
                "🌐 **[Visit the official opportunity "
                f"website →]({official_url})**"
            ),
        )

    if application_url:
        updated = _insert_contextual_link(
            updated,
            r"^##[^\n]*Who can apply[^\n]*$",
            "Open the official application page",
            (
                "🚀 **[Open the official application "
                f"page →]({application_url})**"
            ),
        )

    return updated


def render_opportunity_document(
    metadata: dict[str, Any],
    body: str,
) -> str:
    """Hide machine metadata while keeping the public Markdown readable."""

    body_with_links = _add_contextual_links(
        metadata,
        body,
    )
    clean_body = body_with_links.lstrip("\n").rstrip() + "\n"
    return (
        "<!-- OFFMAP-METADATA\n"
        f"{dump_metadata(metadata)}\n"
        "OFFMAP-METADATA-END -->\n\n"
        f"{clean_body}"
    )
