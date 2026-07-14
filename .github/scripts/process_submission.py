import os
import re
import requests

TOKEN = os.environ["GITHUB_TOKEN"]
REPO = os.environ["REPOSITORY"]
ISSUE_NUMBER = os.environ["ISSUE_NUMBER"]

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
}

# ---------------------------------------------------
# Get Issue
# ---------------------------------------------------

issue = requests.get(
    f"https://api.github.com/repos/{REPO}/issues/{ISSUE_NUMBER}",
    headers=headers,
).json()

body = issue["body"]

# ---------------------------------------------------
# Helper
# ---------------------------------------------------

def extract(label):
    pattern = rf"### {re.escape(label)}\n(.*?)(?=\n### |\Z)"
    match = re.search(pattern, body, re.S)

    if not match:
        return ""

    return match.group(1).strip()

# ---------------------------------------------------
# Extract fields
# ---------------------------------------------------

category = extract("Opportunity category")
title = extract("Opportunity name")
description = extract("Short description")
organizer = extract("Organizer")
website = extract("Official website")
location = extract("Location")
deadline = extract("Application deadline")

print("Submission received:")
print(title)
print(category)
print(location)
print(deadline)
