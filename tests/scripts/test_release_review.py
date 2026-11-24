"""Check the release-branch review gate without making GitHub requests."""

import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_release_automerge import BOT, RELEASED, fake_api, release_pr

import release_review

PATCHED = RELEASED.replace("pytket==2.18.4", "pytket==2.18.5")
RENOVATE = {"ref": "renovate/release/26.1-quantinuum-patch-updates"}
WRITERS = {"maintainer": "write", "admin": "admin", "reader": "read"}


def review(user, state="APPROVED", commit="head"):
    return {"user": {"login": user}, "state": state, "commit_id": commit}


def api_for(pr, reviews=(), **options):
    api = fake_api(pr=pr, **options)
    api.pulls.list_reviews = lambda pull_number, page, per_page: (
        list(reviews) if page == 1 else []
    )
    api.repos.get_collaborator_permission_level = lambda username: {
        "permission": WRITERS.get(username, "none")
    }
    return api


def renovate_pr(**changes):
    pr = release_pr(title="fix(deps): update pytket to v2.18.5")
    pr["head"] = pr["head"] | RENOVATE
    pr.update(changes)
    return pr


def satisfied(api):
    return release_review.review_satisfied(api, 5, BOT)


def test_eligible_release_please_patch_needs_no_review():
    assert satisfied(api_for(release_pr()))


@pytest.mark.parametrize(
    "head,files,eligible",
    [
        (PATCHED, ("pyproject.toml", "uv.lock"), True),
        (RELEASED.replace("pytket==2.18.4", "pytket==2.19.0"), ("uv.lock",), False),
        (RELEASED, ("pyproject.toml", "uv.lock"), False),
        (PATCHED.replace('version = "26.1.0"', 'version = "26.1.1"'), (), False),
        (PATCHED, ("pyproject.toml", "uv.lock", "README.md"), False),
    ],
)
def test_only_renovate_patch_upgrades_skip_review(head, files, eligible):
    api = api_for(renovate_pr(), base=RELEASED, head=head, files=files)
    assert satisfied(api) is eligible


def test_renovate_branch_from_a_fork_requires_review():
    pr = renovate_pr()
    pr["head"] = pr["head"] | {"repo": {"full_name": "fork/repo"}}
    assert not satisfied(api_for(pr, base=RELEASED, head=PATCHED))


@pytest.mark.parametrize(
    "reviews,approved",
    [
        ([review("maintainer")], True),
        ([review("admin")], True),
        ([], False),
        ([review("maintainer", commit="old")], False),
        ([review("reader")], False),
        ([review(BOT)], False),
        ([review("maintainer"), review("admin", "CHANGES_REQUESTED")], False),
        ([review("maintainer", "CHANGES_REQUESTED"), review("maintainer")], True),
        ([review("maintainer"), review("maintainer", "DISMISSED")], False),
        ([review("maintainer"), review("maintainer", "COMMENTED")], True),
    ],
)
def test_other_changes_need_a_writer_approval_of_the_head_commit(reviews, approved):
    pr = release_pr(head=release_pr()["head"] | {"ref": "promote-26.2.0"})
    assert satisfied(api_for(pr, reviews)) is approved


def test_release_please_pr_rejected_by_policy_requires_review(monkeypatch):
    def reject(*_):
        raise ValueError("Package version must belong to the selected release branch")

    monkeypatch.setattr(release_review, "release_pr_eligible", reject)
    assert not satisfied(api_for(release_pr()))


def test_main_prs_are_not_gated():
    pr = release_pr(base=release_pr()["base"] | {"ref": "main"})
    assert satisfied(SimpleNamespace(pulls=SimpleNamespace(get=lambda **_: pr)))


def test_cli_fails_without_approval(tmp_path, monkeypatch):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"number": 5}}))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("RELEASE_BOT", BOT)
    pr = release_pr(head=release_pr()["head"] | {"ref": "promote-26.2.0"})
    monkeypatch.setattr("github_api.create_client", lambda: api_for(pr))
    with pytest.raises(SystemExit) as exit:
        runpy.run_path(str(Path(release_review.__file__)), run_name="__main__")
    assert exit.value.code == 1
