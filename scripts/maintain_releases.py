"""Bootstrap published release branches and refresh the Dependabot support window."""

import json
import os
import subprocess
import tomllib
from pathlib import Path

from ghapi.core import APIError

from github_api import all_items, create_client, read_file
from release_policy import published_series

ROOT = Path(__file__).resolve().parents[1]


def dependabot_config(
    branches: list[str],
    stable: str,
    development: str,
    pre_one: dict[str, list[str]] | None = None,
) -> str:
    result = "version: 2\nupdates:\n" + development
    for branch in branches:
        ignores = "".join(
            f"      - dependency-name: {name}\n"
            "        update-types: ['version-update:semver-minor']\n"
            for name in (pre_one or {}).get(branch, [])
        )
        result += stable.replace("{branch}", branch).replace(
            "    # pre-1.0 ignores\n", ignores
        )
    return result


def expected_dependabot(api) -> str:
    branches = list(published_series(api))[:2]
    pre_one = {}
    for branch in branches:
        project = tomllib.loads(read_file(api, "pyproject.toml", branch))["project"]
        pre_one[branch] = [
            requirement.split("==", 1)[0]
            for requirement in project["dependencies"]
            if requirement.partition("==")[2].startswith("0.")
        ]
    return dependabot_config(
        branches,
        read_file(api, ".github/templates/dependabot-stable.yml", "main"),
        read_file(api, ".github/templates/dependabot-main.yml", "main"),
        pre_one,
    )


def open_files_pr(
    api, base: str, branch: str, files: dict[str, str], title: str, body: str
):
    """Create or update a bot-owned branch without overwriting concurrent pushes."""
    base_sha = api.git.get_ref(ref=f"heads/{base}")["object"]["sha"]
    changed = {}
    for path, content in files.items():
        try:
            old = read_file(api, path, base_sha)
        except APIError as error:
            if error.status_code != 404:
                raise
            old = None
        if old != content:
            changed[path] = content
    if not changed:
        return
    try:
        head = api.git.get_ref(ref=f"heads/{branch}")["object"]["sha"]
    except APIError as error:
        if error.status_code != 404:
            raise
        head = base_sha
        api.git.create_ref(ref=f"refs/heads/{branch}", sha=head)

    def matches(path, content):
        try:
            return read_file(api, path, head) == content
        except APIError as error:
            if error.status_code != 404:
                raise
            return False

    if any(not matches(path, content) for path, content in changed.items()) or (
        head != base_sha
        and api.repos.compare_commits(basehead=f"{base_sha}...{head}")[
            "merge_base_commit"
        ]["sha"]
        != base_sha
    ):
        tree = api.git.create_tree(
            base_tree=api.git.get_commit(commit_sha=base_sha)["tree"]["sha"],
            tree=[
                {"path": path, "mode": "100644", "type": "blob", "content": content}
                for path, content in changed.items()
            ],
        )
        commit = api.git.create_commit(
            message=title,
            tree=tree["sha"],
            parents=[head] if head == base_sha else [head, base_sha],
        )
        api.git.update_ref(ref=f"heads/{branch}", sha=commit["sha"], force=False)
    owner = os.environ["GITHUB_REPOSITORY"].split("/", 1)[0]
    prs = list(
        all_items(api.pulls.list, base=base, head=f"{owner}:{branch}", state="open")
    )
    if not prs:
        pr = api.pulls.create(base=base, head=branch, title=title, body=body)
        print(pr["html_url"])
    else:
        print(prs[0]["html_url"])


def bootstrap(api, branch: str, tag: str):
    try:
        api.git.get_ref(ref=f"heads/{branch}")
    except APIError as error:
        if error.status_code != 404:
            raise
        sha = api.repos.get_commit(ref=tag)["sha"]
        api.git.create_ref(ref=f"refs/heads/{branch}", sha=sha)
    else:
        try:
            read_file(api, "scripts/release_policy.py", branch)
        except APIError as error:
            if error.status_code != 404:
                raise
        else:
            # Existing release branches receive explicit tooling backports.
            return
    paths = subprocess.check_output(
        ["git", "ls-files"], cwd=ROOT, text=True
    ).splitlines()
    files = {
        path: (ROOT / path).read_text()
        for path in paths
        if path.startswith(
            ("scripts/", "tests/scripts/", ".github/workflows/", ".github/templates/")
        )
        or path
        in (
            "MAINTAINING.md",
            "SETUP.md",
            "release-please-config.json",
        )
    }
    config = json.loads(files["release-please-config.json"])
    config["packages"]["."]["initial-version"] = tag[1:].rsplit(".", 1)[0] + ".0"
    files["release-please-config.json"] = json.dumps(config, indent=2) + "\n"
    open_files_pr(
        api,
        branch,
        f"automation/bootstrap-{branch.split('/')[1]}",
        files,
        "chore: enable release branch maintenance",
        f"Install release tooling on {branch}, based on {tag}. Preserve the published dependency pins, lockfile, version, and release manifest.",
    )


def maintain(api):
    series = published_series(api)
    for branch, tag in list(series.items())[:2]:
        bootstrap(api, branch, tag)
    open_files_pr(
        api,
        "main",
        "automation/supported-series",
        {".github/dependabot.yml": expected_dependabot(api)},
        "chore: update automatically maintained release series",
        "Target Dependabot at main and the two most recent published stable series. Older series remain available for manual patches.",
    )


if __name__ == "__main__":
    maintain(create_client())
