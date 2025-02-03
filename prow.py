#!/usr/bin/env python3
# Author: Chmouel Boudjnah <chmouel@redhat.com>
import os
import re
import sys

import requests

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GH_PR_NUM = os.getenv("GH_PR_NUM")
GH_REPO_OWNER = os.getenv("GH_REPO_OWNER")
GH_REPO_NAME = os.getenv("GH_REPO_NAME")
PAC_TRIGGER_COMMENT = os.getenv("PAC_TRIGGER_COMMENT", "")
API_BASE = f"https://api.github.com/repos/{GH_REPO_OWNER}/{GH_REPO_NAME}"
API_ISSUE = f"{API_BASE}/issues/{GH_PR_NUM}"
API_PULLS = f"{API_BASE}/pulls/{GH_PR_NUM}"
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

LGTM_THRESHOLD = 2


def make_request(method, url, data=None):
    if method == "POST":
        return requests.post(url, json=data, headers=HEADERS)
    elif method == "DELETE":
        return requests.delete(url, json=data, headers=HEADERS)
    return None


def assign_unassign(command, values):
    method = "POST" if command == "assign" else "DELETE"
    API_URL = f"{API_PULLS}/requested_reviewers"
    values = [value.lstrip("@") for value in values]
    data = {"reviewers": values}
    return make_request(method, API_URL, data)


def label(values):
    API_URL = f"{API_ISSUE}/labels"
    data = {"labels": values}
    return make_request("POST", API_URL, data)


def unlabel(values):
    for label in values:
        response = make_request("DELETE", f"{API_ISSUE}/labels/{label}")
    return response


def lgtm():
    comments_resp = requests.get(API_ISSUE + "/comments", headers=HEADERS)
    if comments_resp.status_code != 200:
        print(
            f"❌ Failed to fetch comments: {comments_resp.status_code} - {comments_resp.text}",
            file=sys.stderr,
        )
        sys.exit(1)
    comments = comments_resp.json()
    lgtm_users = set()
    for comment_item in comments:
        body = comment_item.get("body", "")
        if re.search(r"^/lgtm\b", body, re.IGNORECASE):
            lgtm_users.add(comment_item["user"]["login"])

    valid_votes = 0
    for user in lgtm_users:
        membership_url = f"{API_BASE}/collaborators/{user}/permission"
        membership_resp = requests.get(membership_url, headers=HEADERS)
        if membership_resp.status_code != 200:
            print(
                f"User {user} does not have admin access (status: {membership_resp.status_code})",
                file=sys.stderr,
            )
            continue
        jeez = membership_resp.json()
        permission = jeez.get("permission")
        if not permission:
            print("No permission found in response", file=sys.stderr)
            continue

        if permission == "admin" or permission == "write":
            valid_votes += 1
        else:
            print(
                f"User {user} does not have write access: {membership_resp.json()}",
                file=sys.stderr,
            )
    if valid_votes >= LGTM_THRESHOLD:
        API_URL = API_PULLS + "/reviews"
        data = {"event": "APPROVE", "body": "LGTM :+1:"}
        print("✅ PR approved with LGTM votes.")
        return make_request("POST", API_URL, data)
    else:
        print(f"Not enough valid /lgtm votes (found {valid_votes}, need 2).")
        sys.exit(0)


def help_command():
    API_URL = f"{API_ISSUE}/comments"
    help_text = """### 🤖 Available Commands
| Command                   | Description                                                          |
|---------------------------|----------------------------------------------------------------------|
| `/assign user1 user2`     | Assigns users for review to the PR                                              |
| `/unassign user1 user2`   | Removes assigned users                                               |
| `/label bug feature`      | Adds labels to the PR                                                |
| `/unlabel bug feature`    | Removes labels from the PR                                           |
| `/lgtm`                   | Approves the PR if at least 2 org members have commented `/lgtm`       |
| `/help`                   | Shows this help message                                              |
"""
    return make_request("POST", API_URL, {"body": help_text})


def check_response(command, values, response):
    if response and response.status_code in [200, 201, 204]:
        print(
            f"✅ Successfully processed {command}: {', '.join(values) if values else ''}"
        )
        return True
    print(
        f"❌ Failed to process {command}: {response.status_code} - {response.text}",
        file=sys.stderr,
    )
    return False


def main():
    match = re.match(
        r"^/(assign|unassign|label|unlabel|lgtm|help)\s*(.*)", PAC_TRIGGER_COMMENT
    )

    if not match:
        print(
            f"⚠️ No valid command found in comment: {PAC_TRIGGER_COMMENT}",
            file=sys.stderr,
        )
        sys.exit(1)

    command, values = match.groups()
    values = values.split()

    if command == "assign":
        response = assign_unassign("assign", values)
    elif command == "unassign":
        response = assign_unassign("unassign", values)
    elif command == "label":
        response = label(values)
    elif command == "unlabel":
        response = unlabel(values)
    elif command == "lgtm":
        response = lgtm()
    elif command == "help":
        response = help_command()

    if not check_response(command, values, response):
        sys.exit(1)


if __name__ == "__main__":
    main()
