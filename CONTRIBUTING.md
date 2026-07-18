# Contributing to OFFMAP

> **Your map. Your story. Your impact.**

OFFMAP helps students find opportunities that would otherwise disappear into group chats, newsletters, and the mysterious depths of someone’s inbox.

You can help by adding opportunities, correcting information, improving the code, or building the parts of the platform that do not exist yet. The map is useful. The roads are still under construction.

---

## Add an Opportunity

Use the OFFMAP submission form:

[**Submit an opportunity →**](../../issues/new?template=submit-opportunity.yml)

You do **not** need to create a Markdown file manually.

The pipeline:

1. preserves the original submission;
2. researches official sources;
3. prepares a draft opportunity page;
4. opens a draft pull request;
5. requires human review before publication.

AI may research, organize, and flag problems. It may not verify or publish an opportunity by itself. We have seen what happens when software becomes overconfident.

### Include

- opportunity name;
- broad category and specific type;
- organizer;
- short description;
- official source;
- deadline;
- format;
- anything useful about eligibility, funding, dates, location, or applications.

A reliable link and a few accurate facts are better than a dramatic paragraph assembled from vibes.

---

## What Belongs Here

OFFMAP includes:

- conferences, summits, forums, and workshops;
- internships, traineeships, and apprenticeships;
- competitions, challenges, and hackathons;
- research programs and placements;
- fellowships and leadership programs;
- scholarships, grants, and travel grants;
- academies, summer schools, courses, and bootcamps;
- startup, accelerator, and entrepreneurship programs;
- creative, writing, media, and design calls;
- exchanges, mobility, and volunteering programs.

OFFMAP does **not** include:

- ordinary job listings;
- referral schemes;
- random promotional webinars;
- listings without a clear organizer or official source;
- tourism packages wearing an educational hat;
- permanently closed opportunities with no sign of returning.

Internships are welcome. General jobs are not.

---

## Correct the Map

Found a broken link, changed deadline, cancelled program, or inaccurate detail?

Submit a correction and include the updated official source.

Do not change published facts without evidence. Confidence is not a citation, no matter how confidently it is typed.

---

## Contribute Code or Documentation

Useful areas include:

- submission and research workflows;
- validation and moderation;
- generated opportunity pages;
- category and subject indexes;
- archives and deadline handling;
- accessibility;
- testing and security;
- documentation;
- the future website and filtering system.

### Current structure

```text
.github/
scripts/
opportunities/
  <main_category>/
    <slug>.md
data/
  opportunities.json
```

Opportunity files live at:

```text
opportunities/<main_category>/<slug>.md
```

Example:

```yaml
main_category: events
category: conference
```

The folder uses `main_category`. The specific `category` stays in the file data.

---

## The Front End Is Not Finished Yet

OFFMAP does **not yet have** the final public pages for:

- Events;
- Conferences and other specific types;
- academic fields and subjects;
- Closing Soon;
- search;
- filter buttons and panels;
- opportunity cards;
- archive pages.

These are planned features.

Future pages should use the existing schema:

```text
main_category
category
format
host_country
eligible_regions
eligible_countries
academic_levels
academic_fields
subjects
audience_groups
funding_features
topics
deadline
```

Contributions to category pages, filters, search, sorting, mobile layouts, and accessibility are especially welcome.

Before adding a major framework, database, or cloud service, open a proposal first. Six filter buttons do not require the infrastructure of a space agency.

---

## Development Workflow

1. Fork the repository.
2. Create a focused branch.
3. Make one clear change.
4. Test it.
5. Open a pull request explaining what changed and why.

Good branch names:

```text
feature/category-pages
feature/opportunity-filters
fix/deadline-validation
docs/update-contributing
```

For Python files, run:

```bash
python -m py_compile scripts/<file>.py
```

When relevant:

```bash
python scripts/build_indexes.py
```

Check that:

- YAML and JSON remain valid;
- `main_category` and `category` stay separate;
- category mismatches are flagged, not silently rewritten;
- filters match their structured fields;
- audience groups come only from submitted dropdown selections;
- human review remains required;
- unrelated files are untouched.

---

## Rules That Must Not Break

### Categories

`main_category` and `category` are separate.

```yaml
main_category: events
category: conference
```

Do not silently replace mismatches with `other`.

### Audience Groups

Audience tags come only from the submitter’s dropdown selections.

Do not infer them from:

- website prose;
- eligibility text;
- images;
- organizer language;
- free-text audience notes;
- model judgment.

Research may flag a selected group as unsupported. It may not add or remove tags.

### Human Review

These values must remain truthful:

```yaml
human_review_required: true
automatically_verified: false
automatically_published: false
```

Merging may record that review was completed. It must not pretend review was never needed.

---

## Write for the Student Applying

Opportunity pages should be:

- accurate;
- easy to scan;
- practical;
- honest about uncertainty;
- clear about deadlines, eligibility, funding, and application links.

Avoid:

- fake urgency;
- invented benefits;
- unsupported prestige claims;
- copied website essays;
- repetitive AI filler;
- decorative language that hides useful details.

OFFMAP can have personality. It still needs to tell people where to apply.

---

## Security

Read [SECURITY.md](SECURITY.md).

Never place secrets, tokens, private information, or credentials in code, issues, pull requests, screenshots, logs, or artifacts.

---

## Help Someone Find the Next Step

A submitted link can become someone’s first conference.

A corrected deadline can save an application.

A better filter can uncover the right opportunity at the right moment.

> **Your map. Your story. Your impact.**

**Find what is possible. Share what should not stay hidden.**
