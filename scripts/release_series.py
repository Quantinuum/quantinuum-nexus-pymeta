"""Create release series previews or prepare a stable release from a published RC."""

import argparse
import json
import os
import re
import subprocess
import tomllib
from pathlib import Path

from ghapi.core import APIError

from github_api import all_items, create_client, set_draft

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"(20\d{2})\.([1-9]\d*)\.0(?:(b|rc)([1-9]\d*))?")


def command(*arguments: str) -> str:
    return subprocess.check_output(arguments, cwd=ROOT, text=True).strip()


def next_preview(target: str, channel: str, tags: list[str]) -> str:
    match = VERSION.fullmatch(target)
    if not match or match[3] or channel not in ("beta", "rc"):
        raise ValueError("Choose a YEAR.SERIES.0 target and beta or rc channel")
    if f"v{target}" in tags:
        raise ValueError("This series has already been released")
    suffix = "b" if channel == "beta" else "rc"
    previews = [VERSION.fullmatch(tag.removeprefix("v")) for tag in tags]
    previews = [item for item in previews if item and item[0].startswith(target)]
    if channel == "beta" and any(item[3] == "rc" for item in previews):
        raise ValueError("The RC freeze has started; beta releases cannot resume")
    numbers = [int(item[4]) for item in previews if item[3] == suffix]
    return f"{target}{suffix}{max(numbers, default=0) + 1}"


def stamp(project_text: str, lock_text: str, version: str) -> tuple[str, str]:
    if not VERSION.fullmatch(version):
        raise ValueError("Invalid release version")
    project = tomllib.loads(project_text)["project"]
    for requirement in project["dependencies"]:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+==[^\s*;]+", requirement):
            raise ValueError("Every runtime dependency must have an exact pin")
    project_text, count = re.subn(
        r'^version = "[^"\n]+"$',
        f'version = "{version}"',
        project_text,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise ValueError("Expected one project version")
    name = re.escape(project["name"])
    lock_text, count = re.subn(
        rf'(\[\[package\]\]\nname = "{name}"\nversion = ")[^"\n]+(")',
        lambda match: match[1] + version + match[2],
        lock_text,
    )
    if count != 1:
        raise ValueError("Expected one metapackage entry in uv.lock")
    return project_text, lock_text


def write_version(version: str, project: str | None = None, lock: str | None = None):
    project, lock = stamp(
        project if project is not None else (ROOT / "pyproject.toml").read_text(),
        lock if lock is not None else (ROOT / "uv.lock").read_text(),
        version,
    )
    (ROOT / "pyproject.toml").write_text(project)
    (ROOT / "uv.lock").write_text(lock)


def commit(message: str):
    command(
        "git",
        "-c",
        "user.name=release-bot",
        "-c",
        "user.email=release-bot@users.noreply.github.com",
        "commit",
        "-m",
        message,
    )


def preview_needed(target: str, channel: str, source: str, tags: list[str]) -> bool:
    suffix = "b" if channel == "beta" else "rc"
    candidates = [
        tag
        for tag in tags
        if re.fullmatch(rf"v{re.escape(target + suffix)}[1-9]\d*", tag)
    ]
    if not candidates:
        return True
    latest = max(candidates, key=lambda tag: int(tag.rsplit(suffix, 1)[1]))
    message = command("git", "show", "-s", "--format=%B", f"{latest}^{{}}")
    previous = re.findall(r"^Preview-Source: ([0-9a-f]{40})$", message, re.MULTILINE)
    if len(previous) != 1:
        raise ValueError("The latest preview must identify one source commit")
    baseline = previous[0]
    if command("git", "merge-base", baseline, source) != baseline:
        raise ValueError("The latest preview source is not an ancestor of next")
    messages = command("git", "log", "--format=%B%x00", f"{baseline}..{source}")
    return any(
        re.match(r"(?:fix|feat)(?:\([^\n()]+\))?!?: .+", message.lstrip("\n"))
        for message in messages.split("\0")
    )


def preview(force: bool = False):
    config = json.loads((ROOT / ".github/preview.json").read_text())
    target, channel = config["target"], config["channel"]
    source = command("git", "rev-parse", "HEAD")
    command("git", "fetch", "origin", "--tags")
    if command("git", "rev-parse", "origin/next") != source:
        print("Skipping an outdated next commit; a newer preview is queued")
        return
    tags = command("git", "tag", "--list").splitlines()
    version = next_preview(target, channel, tags)
    suffix = "b" if channel == "beta" else "rc"
    # Reuse a tag after a partial failure instead of allocating another version.
    for tag in tags:
        if re.fullmatch(rf"v{re.escape(target + suffix)}[1-9]\d*", tag):
            message = command("git", "show", "-s", "--format=%B", f"{tag}^{{}}")
            if f"Preview-Source: {source}" in message.splitlines():
                publish_preview(tag, source)
                return
    if not force and not preview_needed(target, channel, source, tags):
        print("Skipping preview: no fix or feat commits since the last preview")
        return
    write_version(version)
    command("git", "add", "pyproject.toml", "uv.lock")
    commit(f"chore: prepare {version}\n\nPreview-Source: {source}")
    tag = f"v{version}"
    command("git", "tag", tag)
    command("git", "push", "origin", f"refs/tags/{tag}")
    publish_preview(tag, source)


def publish_preview(tag: str, source: str):
    api = create_client()
    try:
        api.repos.get_release_by_tag(tag=tag)
    except APIError as error:
        if error.status_code != 404:
            raise
    else:
        print(
            f"{tag} already exists; retry its Validate and publish workflow if necessary"
        )
        return
    api.git.get_ref(ref=f"tags/{tag}")
    api.repos.create_release(
        tag_name=tag,
        prerelease=True,
        make_latest="false",
        name=tag,
        body=f"Release preview. Source commit: `{source}`.\n\n"
        "Wheel and source distributions are attached after installation checks on all supported platforms. "
        "PyPI publication is optional.",
    )


def validate_candidate(tag: str, release: dict, runs: list[dict], sha: str):
    match = VERSION.fullmatch(tag.removeprefix("v"))
    if not tag.startswith("v") or not match or match[3] != "rc":
        raise ValueError("Promotion requires an RC tag such as v2026.2.0rc1")
    if release["draft"] or not release["prerelease"]:
        raise ValueError("The RC must be a published GitHub prerelease")
    if not any(
        run["head_sha"] == sha and run["conclusion"] == "success" for run in runs
    ):
        raise ValueError(
            "The RC's Validate and publish workflow must succeed before promotion"
        )
    return f"{match[1]}.{match[2]}.0"


def verify_candidate_files(
    project: str, lock: str, candidate_project: str, candidate_lock: str
):
    version = tomllib.loads(project)["project"]["version"]
    expected_project, expected_lock = stamp(candidate_project, candidate_lock, version)
    if tomllib.loads(project) != tomllib.loads(expected_project):
        raise ValueError("Stable package metadata differs from the selected RC")
    if tomllib.loads(lock) != tomllib.loads(expected_lock):
        raise ValueError("Stable dependency lockfile differs from the selected RC")


def verify_promotion():
    project = (ROOT / "pyproject.toml").read_text()
    version = tomllib.loads(project)["project"]["version"]
    match = VERSION.fullmatch(version)
    if not match or match[3]:
        return
    config = json.loads((ROOT / "release-please-config.json").read_text())
    if version == config["packages"]["."]["initial-version"]:
        return
    candidate = json.loads((ROOT / ".github/stable-candidate.json").read_text())
    if candidate["version"] != version or not re.fullmatch(
        r"[0-9a-f]{40}", candidate["sha"]
    ):
        raise ValueError("Release must identify its selected RC")
    if not re.fullmatch(rf"v{re.escape(version)}rc[1-9]\d*", candidate["tag"]):
        raise ValueError("Candidate tag does not match the release")
    sha = command("git", "rev-parse", f"{candidate['tag']}^{{commit}}")
    if sha != candidate["sha"]:
        raise ValueError("The RC tag has changed since promotion")
    verify_candidate_files(
        project,
        (ROOT / "uv.lock").read_text(),
        command("git", "show", f"{sha}:pyproject.toml"),
        command("git", "show", f"{sha}:uv.lock"),
    )


def write_promotion(target: str, tag: str, sha: str, project: str, lock: str):
    write_version(target, project, lock)
    (ROOT / ".github/stable-candidate.json").write_text(
        json.dumps({"version": target, "tag": tag, "sha": sha}, indent=2) + "\n"
    )
    command("git", "add", "pyproject.toml", "uv.lock", ".github/stable-candidate.json")


def promotion_needs_commit(
    head: str, target: str, tag: str, sha: str, project: str, lock: str
) -> bool:
    previous = json.loads(
        command("git", "show", f"{head}:.github/stable-candidate.json")
    )
    old_tag = re.fullmatch(rf"v{re.escape(target)}rc([1-9]\d*)", previous["tag"])
    if previous["version"] != target or not old_tag:
        raise ValueError(
            "The existing promotion branch does not contain a valid candidate for this series"
        )
    if int(tag.rsplit("rc", 1)[1]) < int(old_tag[1]):
        raise ValueError("Cannot replace the selected candidate with an older RC")
    if previous["tag"] == tag and previous["sha"] != sha:
        raise ValueError("The selected RC tag has moved; publish a new RC instead")
    desired_project, desired_lock = stamp(project, lock, target)
    return (
        previous != {"version": target, "tag": tag, "sha": sha}
        or tomllib.loads(command("git", "show", f"{head}:pyproject.toml"))
        != tomllib.loads(desired_project)
        or tomllib.loads(command("git", "show", f"{head}:uv.lock"))
        != tomllib.loads(desired_lock)
    )


def update_promotion(
    api,
    pr: dict,
    branch: str,
    target: str,
    tag: str,
    sha: str,
    project: str,
    lock: str,
    body: str,
):
    if pr["head"]["repo"]["full_name"] != pr["base"]["repo"]["full_name"]:
        raise ValueError("The promotion PR must use a branch in this repository")
    command("git", "fetch", "origin", f"refs/heads/{branch}")
    head = command("git", "rev-parse", "FETCH_HEAD")
    if head != pr["head"]["sha"]:
        raise ValueError(
            "The promotion branch changed; retry with its current revision"
        )
    needs_commit = promotion_needs_commit(head, target, tag, sha, project, lock)
    if not needs_commit and pr["body"] == body and not pr["draft"]:
        print(pr["html_url"])
        return
    number = pr["number"]
    # Keep the PR unmergeable until its candidate, description, and reviews agree.
    if not pr["draft"]:
        set_draft(api, pr["node_id"], True)
    if needs_commit:
        command("git", "switch", "--detach", head)
        write_promotion(target, tag, sha, project, lock)
        commit(f"feat: update release {target} to {tag}\n\n{body}")
        # Append to the reviewed branch; a concurrent push is rejected by Git.
        command("git", "push", "origin", f"HEAD:refs/heads/{branch}")
        head = command("git", "rev-parse", "HEAD")
    api.pulls.update(
        pull_number=number, title=f"feat: prepare release {target}", body=body
    )
    for review in all_items(api.pulls.list_reviews, pull_number=number):
        if review["state"] == "APPROVED" and review["commit_id"] != head:
            api.pulls.dismiss_review(
                pull_number=number,
                review_id=review["id"],
                message=f"Candidate updated to {tag}; approval of the new revision is required.",
            )
    current = api.pulls.get(pull_number=number)
    if (
        current["head"]["sha"] != head
        or not current["draft"]
        or current["state"] != "open"
    ):
        raise ValueError(
            "The promotion PR changed during its update; inspect it before making it ready"
        )
    if not pr["draft"]:
        set_draft(api, pr["node_id"], False)
    print(pr["html_url"])


def promote(tag: str):
    if not re.fullmatch(r"v20\d{2}\.[1-9]\d*\.0rc[1-9]\d*", tag):
        raise ValueError("Promotion requires an RC tag")
    command("git", "fetch", "origin", "--tags")
    sha = command("git", "rev-parse", f"{tag}^{{commit}}")
    api = create_client()
    release = api.repos.get_release_by_tag(tag=tag)
    runs = api.actions.list_workflow_runs(
        workflow_id="publish.yml", head_sha=sha, status="success"
    )
    target = validate_candidate(tag, release, runs["workflow_runs"], sha)
    stable = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    if tuple(map(int, target.split("."))) <= tuple(map(int, stable.split("."))):
        raise ValueError("The release series target must be newer than main")
    branch = f"promote-{target}"
    project = command("git", "show", f"{sha}:pyproject.toml") + "\n"
    lock = command("git", "show", f"{sha}:uv.lock") + "\n"
    if tomllib.loads(project)["project"]["version"] != tag[1:]:
        raise ValueError("The RC tag must match its package version")
    body = (
        f"Promote the exact dependency pins and lockfile from {tag}.\n\n"
        "This release may contain breaking changes.\n\n"
        f"Release-As: {target}"
    )
    owner = os.environ["GITHUB_REPOSITORY"].split("/", 1)[0]
    existing = list(
        all_items(api.pulls.list, head=f"{owner}:{branch}", base="main", state="open")
    )
    if existing:
        update_promotion(
            api, existing[0], branch, target, tag, sha, project, lock, body
        )
        return
    remote = command("git", "ls-remote", "--heads", "origin", f"refs/heads/{branch}")
    if remote:
        command("git", "fetch", "origin", f"refs/heads/{branch}")
        head = command("git", "rev-parse", "FETCH_HEAD")
        needs_commit = promotion_needs_commit(head, target, tag, sha, project, lock)
        command("git", "switch", "--detach", head)
    else:
        command("git", "switch", "-c", branch)
        needs_commit = True
    if needs_commit:
        write_promotion(target, tag, sha, project, lock)
        commit(f"feat: prepare release {target}\n\n{body}")
    command("git", "push", "origin", f"HEAD:refs/heads/{branch}")
    created = api.pulls.create(
        head=branch,
        base="main",
        title=f"feat: prepare release {target}",
        body=body,
    )
    print(created["html_url"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("preview").add_argument("--force", action="store_true")
    subparsers.add_parser("promote").add_argument("tag")
    subparsers.add_parser("verify-promotion")
    args = parser.parse_args()
    if args.action == "preview":
        preview(force=args.force or os.environ.get("PREVIEW_FORCE") == "true")
    elif args.action == "promote":
        promote(args.tag)
    else:
        verify_promotion()
