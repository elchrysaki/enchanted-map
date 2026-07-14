import base64
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
import requests

GITHUB_API = "https://api.github.com"

TOKEN = os.environ["GITHUB_TOKEN"]

REPOSITORY = os.environ["REPOSITORY"]

ISSUE_NUMBER = os.environ["ISSUE_NUMBER"]

OPPORTUNITY_FILE = Path(os.environ["OPPORTUNITY_FILE"])

BASE_BRANCH = os.environ.get("BASE_BRANCH", "main")

BRANCH_PREFIX = os.environ.get(

    "BRANCH_PREFIX",

    "automated-discovery",

)

HEADERS = {

    "Authorization": f"Bearer {TOKEN}",

    "Accept": "application/vnd.github+json",

    "X-GitHub-Api-Version": "2022-11-28",

}

def fail(message: str) -> None:

    print(f"::error::{message}")

    raise SystemExit(1)

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

            f"GitHub API request failed: "

            f"{method} {endpoint} returned "

            f"{response.status_code}\n"

            f"{response.text[:1500]}"

        )

    return response

def slugify(value: str) -> str:

    value = value.lower().strip()

    value = re.sub(r"[^a-z0-9]+", "-", value)

    return value.strip("-")

def read_generated_file() -> str:

    if not OPPORTUNITY_FILE.exists():

        fail(

            f"Generated opportunity file does not exist: "

            f"{OPPORTUNITY_FILE}"

        )

    content = OPPORTUNITY_FILE.read_text(

        encoding="utf-8",

    )

    if not content.strip():

        fail(

            f"Generated opportunity file is empty: "

            f"{OPPORTUNITY_FILE}"

        )

    return content

def read_front_matter_title(content: str) -> str:

    match = re.search(

        r"^---\s*\n(.*?)\n---",

        content,

        re.DOTALL,

    )

    if not match:

        return OPPORTUNITY_FILE.stem.replace("-", " ").title()

    front_matter = match.group(1)

    title_match = re.search(

        r'^title:\s*["\']?(.*?)["\']?\s*$',

        front_matter,

        re.MULTILINE,

    )

    if not title_match:

        return OPPORTUNITY_FILE.stem.replace("-", " ").title()

    return title_match.group(1).strip()

def get_base_branch_sha() -> str:

    response = github_request(

        "GET",

        f"/repos/{REPOSITORY}/git/ref/heads/{BASE_BRANCH}",

    )

    data = response.json()

    try:

        return data["object"]["sha"]

    except (KeyError, TypeError):

        fail(

            f"Could not determine SHA for base branch "

            f"{BASE_BRANCH}."

        )

    return ""

def branch_exists(branch_name: str) -> bool:

    response = requests.get(

        f"{GITHUB_API}/repos/{REPOSITORY}/git/ref/heads/"

        f"{branch_name}",

        headers=HEADERS,

        timeout=30,

    )

    if response.status_code == 200:

        return True

    if response.status_code == 404:

        return False

    fail(

        f"Could not check branch existence: "

        f"{response.status_code} {response.text[:1000]}"

    )

    return False

def create_branch(

    branch_name: str,

    base_sha: str,

) -> None:

    github_request(

        "POST",

        f"/repos/{REPOSITORY}/git/refs",

        expected_statuses=(201,),

        json={

            "ref": f"refs/heads/{branch_name}",

            "sha": base_sha,

        },

    )

    print(f"Created branch: {branch_name}")

def get_existing_file_sha(

    repository_path: str,

    branch_name: str,

) -> str | None:

    response = requests.get(

        f"{GITHUB_API}/repos/{REPOSITORY}/contents/"

        f"{repository_path}",

        headers=HEADERS,

        params={"ref": branch_name},

        timeout=30,

    )

    if response.status_code == 404:

        return None

    if response.status_code != 200:

        fail(

            f"Could not inspect existing file: "

            f"{response.status_code} {response.text[:1000]}"

        )

    data = response.json()

    sha = data.get("sha")

    return sha if isinstance(sha, str) else None

def commit_opportunity_file(

    branch_name: str,

    repository_path: str,

    content: str,

    title: str,

) -> None:

    encoded_content = base64.b64encode(

        content.encode("utf-8")

    ).decode("ascii")

    payload: dict[str, Any] = {

        "message": (

            f"Add opportunity: {title} "

            f"(submission #{ISSUE_NUMBER})"

        ),

        "content": encoded_content,

        "branch": branch_name,

    }

    existing_sha = get_existing_file_sha(

        repository_path,

        branch_name,

    )

    if existing_sha:

        payload["sha"] = existing_sha

    github_request(

        "PUT",

        f"/repos/{REPOSITORY}/contents/{repository_path}",

        expected_statuses=(200, 201),

        json=payload,

    )

    print(f"Committed file: {repository_path}")

def find_existing_pull_request(

    branch_name: str,

) -> dict[str, Any] | None:

    owner = REPOSITORY.split("/", 1)[0]

    response = github_request(

        "GET",

        f"/repos/{REPOSITORY}/pulls",

        params={

            "state": "open",

            "head": f"{owner}:{branch_name}",

            "base": BASE_BRANCH,

        },

    )

    pull_requests = response.json()

    if (

        isinstance(pull_requests, list)

        and pull_requests

    ):

        return pull_requests[0]

    return None

def build_pull_request_body(

    title: str,

    repository_path: str,

) -> str:

    return f"""## 🗺️ A New Discovery Awaits Review

This pull request was generated automatically from issue #{ISSUE_NUMBER}.

### ✨ Proposed opportunity

**{title}**

### 📜 Generated file

`{repository_path}`

### 🛡️ Moderator checklist

- [ ] Confirm the opportunity exists on an official source

- [ ] Verify the application deadline

- [ ] Verify geographic eligibility

- [ ] Verify academic levels and relevant majors

- [ ] Verify funding, fees, and participant support

- [ ] Verify any identity-focused or priority-audience claims

- [ ] Check that AI-generated tags are accurate

- [ ] Remove or correct unsupported information

- [ ] Mark the opportunity as reviewed before merging

### 🤖 Automation notice

The submission was parsed and formatted with AI assistance.

AI did not verify the opportunity and cannot merge this pull request.

Closes #{ISSUE_NUMBER}

"""

def create_pull_request(

    branch_name: str,

    title: str,

    repository_path: str,

) -> dict[str, Any]:

    existing = find_existing_pull_request(

        branch_name

    )

    if existing:

        print(

            f"Pull request already exists: "

            f"{existing.get('html_url')}"

        )

        return existing

    response = github_request(

        "POST",

        f"/repos/{REPOSITORY}/pulls",

        expected_statuses=(201,),

        json={

            "title": f"🗺️ Add {title}",

            "head": branch_name,

            "base": BASE_BRANCH,

            "body": build_pull_request_body(

                title,

                repository_path,

            ),

            "draft": True,

            "maintainer_can_modify": True,

        },

    )

    pull_request = response.json()

    print(

        f"Created draft pull request: "

        f"{pull_request.get('html_url')}"

    )

    return pull_request

def ensure_label(

    label_name: str,

    color: str,

    description: str,

) -> None:

    response = requests.get(

        f"{GITHUB_API}/repos/{REPOSITORY}/labels/"

        f"{label_name}",

        headers=HEADERS,

        timeout=30,

    )

    if response.status_code == 200:

        return

    if response.status_code != 404:

        fail(

            f"Could not check label {label_name}: "

            f"{response.status_code} {response.text[:500]}"

        )

    github_request(

        "POST",

        f"/repos/{REPOSITORY}/labels",

        expected_statuses=(201,),

        json={

            "name": label_name,

            "color": color,

            "description": description,

        },

    )

def add_labels(

    issue_or_pr_number: int,

    labels: list[str],

) -> None:

    github_request(

        "POST",

        (

            f"/repos/{REPOSITORY}/issues/"

            f"{issue_or_pr_number}/labels"

        ),

        expected_statuses=(200,),

        json={"labels": labels},

    )

def comment_on_issue(

    pull_request_url: str,

) -> None:

    marker = "<!-- enchanted-map-generated-pr -->"

    comments_response = github_request(

        "GET",

        (

            f"/repos/{REPOSITORY}/issues/"

            f"{ISSUE_NUMBER}/comments"

        ),

    )

    comments = comments_response.json()

    if isinstance(comments, list):

        for comment in comments:

            body = comment.get("body", "")

            if marker in body:

                print(

                    "Pull-request comment already exists."

                )

                return

    body = f"""{marker}

## 📜 Your Discovery Has Become a Draft

The automation created a reviewable pull request:

➡️ {pull_request_url}

A human moderator must verify the facts before it may enter the Enchanted Map.

The pull request is currently a **draft**, so it cannot be merged accidentally while still wearing its AI-generated training wheels.

"""

    github_request(

        "POST",

        (

            f"/repos/{REPOSITORY}/issues/"

            f"{ISSUE_NUMBER}/comments"

        ),

        expected_statuses=(201,),

        json={"body": body},

    )

def write_github_output(

    name: str,

    value: str,

) -> None:

    output_file = os.environ.get("GITHUB_OUTPUT")

    if not output_file:

        print(f"{name}={value}")

        return

    with open(

        output_file,

        "a",

        encoding="utf-8",

    ) as output:

        output.write(f"{name}={value}\n")

def main() -> None:

    content = read_generated_file()

    title = read_front_matter_title(content)

    repository_path = (

        OPPORTUNITY_FILE.as_posix()

    )

    slug = slugify(title)

    branch_name = (

        f"{BRANCH_PREFIX}/"

        f"issue-{ISSUE_NUMBER}-{slug}"

    )

    if len(branch_name) > 200:

        branch_name = branch_name[:200].rstrip("-")

    if not branch_exists(branch_name):

        base_sha = get_base_branch_sha()

        create_branch(

            branch_name,

            base_sha,

        )

    else:

        print(

            f"Branch already exists: {branch_name}"

        )

    commit_opportunity_file(

        branch_name,

        repository_path,

        content,

        title,

    )

    pull_request = create_pull_request(

        branch_name,

        title,

        repository_path,

    )

    try:

        pull_request_number = int(

            pull_request["number"]

        )

        pull_request_url = str(

            pull_request["html_url"]

        )

    except (KeyError, TypeError, ValueError):

        fail(

            "GitHub returned an invalid pull-request response."

        )

    ensure_label(

        "generated-discovery",

        "8B5CF6",

        "Automatically generated from an opportunity submission.",

    )

    ensure_label(

        "needs-maintainer-review",

        "F4C542",

        "Requires factual verification by a human maintainer.",

    )

    add_labels(

        pull_request_number,

        [

            "generated-discovery",

            "needs-maintainer-review",

        ],

    )

    ensure_label(

        "pull-request-created",

        "2DA44E",

        "A reviewable pull request was created for this submission.",

    )

    add_labels(

        int(ISSUE_NUMBER),

        ["pull-request-created"],

    )

    comment_on_issue(

        pull_request_url

    )

    write_github_output(

        "pull_request_number",

        str(pull_request_number),

    )

    write_github_output(

        "pull_request_url",

        pull_request_url,

    )

    write_github_output(

        "branch_name",

        branch_name,

    )

    print(

        f"Reviewable draft pull request ready: "

        f"{pull_request_url}"

    )

if __name__ == "__main__":

    try:

        main()

    except requests.RequestException as exc:

        fail(f"Network request failed: {exc}")

    except KeyboardInterrupt:

        sys.exit(130)
