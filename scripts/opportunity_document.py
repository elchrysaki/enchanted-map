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


def render_opportunity_document(
    metadata: dict[str, Any],
    body: str,
) -> str:
    """Hide machine metadata while keeping the public Markdown readable."""

    clean_body = body.lstrip("\n").rstrip() + "\n"
    return (
        "<!-- OFFMAP-METADATA\n"
        f"{dump_metadata(metadata)}\n"
        "OFFMAP-METADATA-END -->\n\n"
        f"{clean_body}"
    )
