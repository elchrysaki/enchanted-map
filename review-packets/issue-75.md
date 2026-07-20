<!-- offmap-review-packet -->
# OffMap moderator review for issue #75

> [!WARNING]
> This file is a review packet, not a published opportunity. A human must
> verify the evidence and decide what happens next.

## Processing outcome

**Outcome:** `automation-recovery-required`

The researched record could not be converted into publishable structured content.

## Original submission

- **Issue:** [[Discovery]: Vision Weekend USA 2026](https://github.com/elchrysaki/offmap-hub/issues/75)
- **Submitted by:** `elchrysaki`
- **Processed at:** `2026-07-20T09:29:42.756861+00:00`
- **Original issue preserved:** Yes

## Workflow stages

| Stage | Result | Detail |
|---|---|---|
| Severe-risk preflight | `continue` | none |
| Intake | `success` | safe_to_research=true |
| Official research | `success` | continue-to-human-review |
| Category reconciliation | `success` | keeps main and specific categories paired |
| Formatting | `failure` | no recommendation |
| Opportunity generation | `skipped` | safe_to_generate=not set |
| Moderator report | `skipped` | report is included when available |

## Human tasks

1. Inspect the researched JSON and formatting error.
2. Correct missing or incompatible fields.
3. Rerun formatting or prepare the page manually.

## Available processing records

- `artifacts/raw-submission-75.json`
- `artifacts/researched-submission-75.json`

## Important rules

- Official current evidence takes precedence over contributor claims.
- Contributor values remain preserved in the original issue and raw record.
- Conflicts should be corrected in the draft and explained, not hidden.
- `audience.groups` remains controlled only by the submitted dropdown.
- Nothing is published until a human approves and merges a valid page.



## Processing log excerpts

### `risk.log`

```text
Preflight risk classification passed. The submission may continue to intake and research.

```

### `intake.log`

```text
Raw submission preserved successfully.
Raw record path: artifacts/raw-submission-75.json
Main category routing hint: events
Specific category routing hint: conference
Assigned moderators: elchrysaki

```

### `research.log`

```text
Researched submission created successfully.
Research output: artifacts/researched-submission-75.json
Search enabled: True

```

### `reconcile.log`

```text
Researched category pair already matched.

```

### `formatter.log`

```text
::error::'funding.other_support' must contain only strings.

```