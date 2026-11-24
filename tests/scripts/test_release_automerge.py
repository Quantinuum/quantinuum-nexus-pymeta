"""Check release PR auto-merge eligibility without making GitHub requests."""

import base64
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from ghapi.core import APIError

import release_automerge

RELEASED = """[project]
name = "quantinuum-nexus"
version = "26.1.0"
dependencies = [
  "guppylang==1.1.3",
  "guppyft==0.4.0",
  "pytket==2.18.4",
  "hugr==0.18.8",
]
"""
BOT = "release-bot"


def release_pr(**changes):
    pr = {
        "number": 5,
        "state": "open",
        "draft": False,
        "auto_merge": None,
        "user": {"login": BOT},
        "base": {
            "ref": "release/26.1",
            "sha": "base",
            "repo": {"full_name": "owner/repo"},
        },
        "head": {
            "ref": "release-please--branches--release/26.1",
            "sha": "head",
            "repo": {"full_name": "owner/repo"},
        },
    }
    pr.update(changes)
    return pr


def fake_api(
    pr=None,
    base=RELEASED,
    head=None,
    released=RELEASED,
    manifest=None,
    files=(
        "pyproject.toml",
        "uv.lock",
        "CHANGELOG.md",
        ".release-please-manifest.json",
    ),
    releases=("v26.1.0",),
):
    head = head or base.replace('version = "26.1.0"', 'version = "26.1.1"')
    contents = {
        ("pyproject.toml", "base"): base,
        ("pyproject.toml", "head"): head,
        (".release-please-manifest.json", "base"): json.dumps(
            {".": "26.1.0"} if manifest is None else manifest
        ),
    }

    def get_content(path, ref):
        if ref.startswith("v"):
            if released is None:
                raise APIError("Not Found", status_code=404)
            text = released
        else:
            text = contents[path, ref]
        return {
            "encoding": "base64",
            "content": base64.b64encode(text.encode()).decode(),
        }

    return SimpleNamespace(
        pulls=SimpleNamespace(
            get=Mock(return_value=pr or release_pr()),
            list_files=lambda pull_number, page, per_page: (
                [{"filename": name} for name in files] if page == 1 else []
            ),
        ),
        repos=SimpleNamespace(
            get_content=get_content,
            list_releases=lambda page, per_page: (
                [
                    {"tag_name": tag, "draft": False, "prerelease": False}
                    for tag in releases
                ]
                if page == 1
                else []
            ),
        ),
    )


def queue(api, monkeypatch):
    run = Mock()
    monkeypatch.setattr(release_automerge.subprocess, "run", run)
    release_automerge.queue_release(api, 5, BOT, "owner/repo")
    return [call.args[0] for call in run.call_args_list]


def test_queues_a_patch_release_with_a_head_commit_guard(monkeypatch):
    assert queue(fake_api(), monkeypatch) == [
        [
            "gh",
            "pr",
            "merge",
            "5",
            "--repo",
            "owner/repo",
            "--auto",
            "--squash",
            "--match-head-commit",
            "head",
        ]
    ]


@pytest.mark.parametrize(
    "pin,automatic",
    [
        ("pytket==2.18.5", True),
        ("hugr==0.18.9", True),
        ("pytket==2.19.0", False),
        ("pytket==3.0.0", False),
        ("pytket==2.18.3", False),
        ("hugr==0.19.0", False),
    ],
)
def test_checks_every_pin_against_the_previous_release(monkeypatch, pin, automatic):
    name = pin.split("==")[0]
    old = next(line for line in RELEASED.splitlines() if f'"{name}==' in line)
    updated = RELEASED.replace(old, f'  "{pin}",')
    assert bool(queue(fake_api(base=updated), monkeypatch)) is automatic


def test_added_pins_and_mixed_minor_updates_require_review(monkeypatch):
    added = RELEASED.replace('  "hugr', '  "tket==0.15.15",\n  "hugr')
    mixed = RELEASED.replace("pytket==2.18.4", "pytket==2.19.0").replace(
        "hugr==0.18.8", "hugr==0.18.9"
    )
    assert not queue(fake_api(base=added), monkeypatch)
    assert not queue(fake_api(base=mixed), monkeypatch)


@pytest.mark.parametrize(
    "options",
    [
        {"pr": release_pr(user={"login": "someone"})},
        {"pr": release_pr(draft=True)},
        {
            "pr": release_pr(
                base={"ref": "main", "sha": "base", "repo": {"full_name": "owner/repo"}}
            )
        },
        {"files": ("pyproject.toml", "scripts/release_policy.py")},
        {"head": RELEASED.replace('version = "26.1.0"', 'version = "26.2.0"')},
        {"manifest": {}},
        {"released": None},
        {"releases": ("v26.1.0", "v26.2.0", "v26.3.0")},
    ],
)
def test_other_release_prs_require_manual_review(monkeypatch, options):
    assert not queue(fake_api(**options), monkeypatch)


def test_disables_auto_merge_when_a_release_pr_becomes_ineligible(monkeypatch):
    api = fake_api(
        pr=release_pr(auto_merge={"merge_method": "squash"}),
        base=RELEASED.replace("pytket==2.18.4", "pytket==2.19.0"),
    )
    assert queue(api, monkeypatch) == [
        ["gh", "pr", "merge", "5", "--repo", "owner/repo", "--disable-auto"]
    ]


def test_reevaluation_happens_with_auto_merge_disabled(monkeypatch):
    api = fake_api(pr=release_pr(auto_merge={"merge_method": "squash"}))
    api.repos.get_content = Mock(side_effect=APIError("Unavailable", status_code=503))
    run = Mock()
    monkeypatch.setattr(release_automerge.subprocess, "run", run)
    with pytest.raises(APIError):
        release_automerge.queue_release(api, 5, BOT, "owner/repo")
    assert [call.args[0][-1] for call in run.call_args_list] == ["--disable-auto"]


def test_a_release_pr_whose_checks_passed_is_merged_directly(monkeypatch):
    api = fake_api(pr=release_pr(mergeable_state="clean"))
    assert queue(api, monkeypatch) == [
        [
            "gh",
            "pr",
            "merge",
            "5",
            "--repo",
            "owner/repo",
            "--squash",
            "--match-head-commit",
            "head",
        ]
    ]


@pytest.mark.parametrize(
    "before,after,allowed",
    [
        ("26.12.0", "26.12.1", True),
        ("26.12.1", "26.13.0", False),
        ("26.12.1", "27.1.0", False),
    ],
)
def test_patch_releases_keep_the_same_year_and_series(before, after, allowed):
    base = RELEASED.replace('version = "26.1.0"', f'version = "{before}"')
    head = RELEASED.replace('version = "26.1.0"', f'version = "{after}"')
    assert (
        release_automerge.release_update_allowed(base, head, {".": before}) == allowed
    )
