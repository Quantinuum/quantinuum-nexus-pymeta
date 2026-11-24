"""Create release series previews or prepare a stable release from a published RC."""

import argparse
import json
import os
import re
import subprocess
import tomllib
from pathlib import Path

from ghapi.core import APIError

from dispatch_release import dispatch_release
from github_api import all_items, create_client, get_release, set_draft
from release_policy import published_series, release_branch

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"([1-9]\d)\.([1-9]\d*)\.0(?:(b|rc)([1-9]\d*))?")


def command(*arguments: str) -> str:
    return subprocess.check_output(arguments, cwd=ROOT, text=True).strip()


def check_selection(target: str, channel: str):
    match = VERSION.fullmatch(target)
    if not match or match[3] or channel not in ("beta", "rc"):
        raise ValueError("Choose a YY.SERIES.0 target and beta or rc channel")


def next_preview(target: str, channel: str, tags: list[str]) -> str:
    check_selection(target, channel)
    if f"v{target}" in tags:
        raise ValueError("This series has already been released")
    suffix = "b" if channel == "beta" else "rc"
    previews = [VERSION.fullmatch(tag.removeprefix("v")) for tag in tags]
    previews = [item for item in previews if item and item[0].startswith(target)]
    if channel == "beta" and any(item[3] == "rc" for item in previews):
        raise ValueError("The RC freeze has started; beta releases cannot resume")
    numbers = [int(item[4]) for item in previews if item[3] == suffix]
    return f"{target}{suffix}{max(numbers, default=0) + 1}"


def check_preview(config: dict, tags: list[str]):
    """Reject a preview selection that the Preview workflow would fail on after merging."""
    if set(config) != {"target", "channel"} or not all(
        isinstance(value, str) for value in config.values()
    ):
        raise ValueError("preview.json must contain only a target and a channel")
    check_selection(config["target"], config["channel"])
    # Previews of a released series are skipped until main selects the next target.
    if f"v{config['target']}" not in tags:
        next_preview(config["target"], config["channel"], tags)


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
        raise ValueError("The latest preview source is not an ancestor of main")
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
    if command("git", "rev-parse", "origin/main") != source:
        print("Skipping an outdated main commit; a newer preview is queued")
        return
    tags = command("git", "tag", "--list").splitlines()
    if f"v{target}" in tags:
        print(
            "Skipping preview: this series is stable; select the next preview target on main"
        )
        return
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
        existing = get_release(api, tag)
    except APIError as error:
        if error.status_code != 404:
            raise
    else:
        if existing["draft"]:
            dispatch_release(api, tag)
        else:
            print(
                f"{tag} already exists; retry its Validate and publish workflow if necessary"
            )
        return
    api.git.get_ref(ref=f"tags/{tag}")
    api.repos.create_release(
        tag_name=tag,
        draft=True,
        prerelease=True,
        make_latest="false",
        name=tag,
        body=f"Release preview. Source commit: `{source}`.\n\n"
        "Wheel and source distributions are attached after installation checks on all supported platforms. "
        "PyPI publication is optional.",
    )

    dispatch_release(api, tag)


def validate_candidate(tag: str, release: dict, runs: list[dict], sha: str):
    match = VERSION.fullmatch(tag.removeprefix("v"))
    if not tag.startswith("v") or not match or match[3] != "rc":
        raise ValueError("Promotion requires an RC tag such as v26.2.0rc1")
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


def previous_series_start(target: str, sha: str) -> str | None:
    """Return the commit on main where the latest older stable series branched."""
    series = tuple(map(int, target.split(".")[:2]))
    stable = []
    for tag in command("git", "tag", "--list", "v*").split():
        match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", tag)
        if match and (int(match[1]), int(match[2])) < series:
            stable.append((tuple(map(int, match.groups())), tag))
    if not stable:
        return None
    tag = max(stable)[1]
    # Promotion squashes the selected RC into the release branch, so the stable
    # tag's ancestry can end at an earlier RC of that series.
    try:
        start = json.loads(
            command("git", "show", f"{tag}:.github/stable-candidate.json")
        )["sha"]
    except subprocess.CalledProcessError:
        start = f"{tag}^{{commit}}"
    return command("git", "merge-base", sha, start)


def contains(head: str, sha: str) -> bool:
    return not subprocess.run(
        ["git", "merge-base", "--is-ancestor", sha, head], cwd=ROOT
    ).returncode


def start_promotion(head: str, sha: str):
    """Check out head with the RC's complete tree for the next promotion commit.

    The release branch is created at the first promoted RC. A later RC is
    recorded as a merge parent so that its other changes reach the release.
    """
    command("git", "switch", "--detach", head)
    if not contains(head, sha):
        command("git", "merge", "--no-ff", "--no-commit", "--strategy", "ours", sha)
        command("git", "read-tree", "--reset", "-u", sha)


def write_promotion(target: str, tag: str, sha: str, project: str, lock: str):
    write_version(target, project, lock)
    (ROOT / ".github/stable-candidate.json").write_text(
        json.dumps({"version": target, "tag": tag, "sha": sha}, indent=2) + "\n"
    )
    config_path = ROOT / "release-please-config.json"
    config = json.loads(config_path.read_text())
    config["packages"]["."]["initial-version"] = target
    # The new branch has no release in its history, so Release Please collects
    # commits back to this point; start after the previous series branched.
    start = previous_series_start(target, sha)
    if start:
        config["bootstrap-sha"] = start
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    (ROOT / ".release-please-manifest.json").write_text("{}\n")
    command(
        "git",
        "add",
        "pyproject.toml",
        "uv.lock",
        ".github/stable-candidate.json",
        "release-please-config.json",
        ".release-please-manifest.json",
    )


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
        or not contains(head, sha)
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
        start_promotion(head, sha)
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
    if not re.fullmatch(r"v[1-9]\d\.[1-9]\d*\.0rc[1-9]\d*", tag):
        raise ValueError("Promotion requires an RC tag")
    command("git", "fetch", "origin", "--tags")
    sha = command("git", "rev-parse", f"{tag}^{{commit}}")
    api = create_client()
    release = get_release(api, tag)
    runs = api.actions.list_workflow_runs(
        workflow_id="publish.yml", head_sha=sha, status="success"
    )
    target = validate_candidate(tag, release, runs["workflow_runs"], sha)
    series = published_series(api)
    if series and tuple(map(int, target.split("."))) <= tuple(
        map(int, next(iter(series.values()))[1:].split("."))
    ):
        raise ValueError(
            "The release series target must be newer than published stable series"
        )
    base_branch = release_branch(target)
    remote_base = command(
        "git", "ls-remote", "--heads", "origin", f"refs/heads/{base_branch}"
    )
    if not remote_base:
        command("git", "push", "origin", f"{sha}:refs/heads/{base_branch}")
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
        all_items(
            api.pulls.list, head=f"{owner}:{branch}", base=base_branch, state="open"
        )
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
    else:
        command("git", "fetch", "origin", f"refs/heads/{base_branch}")
        head = command("git", "rev-parse", "FETCH_HEAD")
        needs_commit = True
    if needs_commit:
        start_promotion(head, sha)
        write_promotion(target, tag, sha, project, lock)
        commit(f"feat: prepare release {target}\n\n{body}")
    else:
        command("git", "switch", "--detach", head)
    command("git", "push", "origin", f"HEAD:refs/heads/{branch}")
    created = api.pulls.create(
        head=branch,
        base=base_branch,
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
    subparsers.add_parser("check-preview")
    args = parser.parse_args()
    if args.action == "preview":
        preview(force=args.force or os.environ.get("PREVIEW_FORCE") == "true")
    elif args.action == "promote":
        promote(args.tag)
    elif args.action == "check-preview":
        check_preview(
            json.loads((ROOT / ".github/preview.json").read_text()),
            [tag["name"] for tag in all_items(create_client().repos.list_tags)],
        )
    else:
        verify_promotion()
