# Security Policy

Thank you for helping keep OFFMAP and its community safe.

OFFMAP accepts public opportunity submissions and uses automated workflows to preserve, research, format, review, and prepare proposed repository content.

Security reports concerning these workflows, repository permissions, generated files, review safeguards, contributor data, or publication controls are welcome.

## Supported Versions

OFFMAP is currently under active development.

| Version | Supported |
|---|---|
| Latest version on `main` | Yes |
| Older commits or abandoned branches | No |
| Forks and unofficial deployments | No |

Security fixes are applied to the latest version of the repository rather than maintained as separate release branches.

## Reporting a Vulnerability

Do not report security vulnerabilities through a public GitHub issue, discussion, opportunity submission, or pull request.

Please use GitHub's private vulnerability-reporting feature:

1. Open the repository's **Security** section.
2. Select **Advisories**.
3. Select **Report a vulnerability**.
4. Submit the report privately.

If private vulnerability reporting is temporarily unavailable, contact the repository owner through their GitHub profile without publicly sharing exploit details, credentials, tokens, private data, or step-by-step attack instructions.

## What to Include

A useful report should contain:

- A clear description of the vulnerability.
- The affected workflow, script, file, or repository feature.
- The potential security impact.
- Reproduction steps or a minimal proof of concept.
- Any conditions required for the vulnerability to work.
- Suggested mitigation steps, when available.
- Whether the vulnerability has been disclosed elsewhere.

Please remove or redact personal information, access tokens, API keys, private submission data, and unrelated credentials.

## Security Issues Within Scope

Examples of relevant security reports include:

- GitHub Actions command injection.
- Malicious issue content causing unintended code execution.
- Prompt injection that results in unauthorized repository changes.
- Path traversal or writing files outside approved directories.
- Exposure of GitHub tokens, API keys, secrets, or workflow artifacts.
- Workflows receiving permissions broader than necessary.
- Unauthorized branch, commit, issue, label, comment, or pull-request creation.
- Unauthorized modification of opportunity pages or generated indexes.
- Bypassing moderator review or the `safe_to_generate_draft_page` safeguard.
- Publishing an opportunity without the required human approval.
- Unsafe processing of contributor-supplied URLs or file content.
- Cross-submission file overwrites or branch contamination.
- Dependency vulnerabilities that can realistically affect this repository.
- Disclosure of information that was intended to remain private.

## Issues Outside Security Scope

The following are generally not security vulnerabilities:

- Incorrect, incomplete, expired, or misleading opportunity information.
- AI-generated factual errors without a security impact.
- Spam submissions.
- Broken links.
- Formatting or accessibility problems.
- Workflow failures that do not expose data or grant unauthorized access.
- Disagreements about moderation decisions.
- Feature requests.
- Missing opportunities or delayed updates.

These should be reported through the repository's normal issue system.

## Response Process

The maintainer will aim to:

- Acknowledge a valid report within five business days.
- Assess its severity and likely impact.
- Request additional information when necessary.
- Prepare and test a correction.
- Coordinate disclosure with the reporter when appropriate.
- Credit the reporter unless they prefer to remain anonymous.

Response times may vary because the project is maintained by volunteers.

Reports involving leaked credentials, active exploitation, unauthorized repository access, bypassed publication controls, or exposed personal information will receive priority.

## Responsible Disclosure

Please allow reasonable time for investigation and remediation before publicly disclosing a vulnerability.

Do not:

- Access, alter, or delete data belonging to other people.
- Expose secrets or personal information publicly.
- Disrupt repository availability or GitHub services.
- Use automated testing that creates excessive issues, branches, pull requests, comments, labels, artifacts, or workflow runs.
- Continue testing after confirming that a vulnerability exists.
- Exploit a vulnerability beyond what is necessary to demonstrate its impact.
- Attempt to publish or modify real opportunity records as part of testing.

## Good-Faith Research

Security research performed responsibly and in good faith is appreciated.

OFFMAP will not pursue action against researchers who:

- Follow this policy.
- Avoid harming users, contributors, or infrastructure.
- Report findings privately.
- Limit testing to what is necessary.
- Provide reasonable time for remediation.

This policy does not authorize activity that violates applicable law, GitHub's terms, or the rights of third parties.

## Protecting Secrets

Never include real credentials in:

- GitHub issues.
- Pull requests.
- Opportunity submissions.
- Workflow logs.
- Example configuration files.
- Screenshots.
- Test fixtures.
- Uploaded processing artifacts.

If a secret is accidentally committed or exposed, revoke or rotate it immediately.

Removing it from the latest commit alone is not sufficient because it may remain in Git history, caches, logs, workflow artifacts, or forks.

Thank you for helping protect OFFMAP, its contributors, and the students who rely on it.
