"""Check the RC dependency freeze gate without making GitHub requests."""

import json
import runpy
from pathlib import Path
from unittest.mock import Mock

import pytest

import dependency_freeze

BETA = {"target": "26.2.0", "channel": "beta"}
RC = {"target": "26.2.0", "channel": "rc"}


LOCK = {"pyproject.toml", "uv.lock"}
WORKFLOW = {".github/workflows/ci.yml", "renovate.json"}


@pytest.mark.parametrize(
    "base,head,preview,files,blocked",
    [
        ("main", "renovate/quantinuum-packages", RC, LOCK, True),
        ("main", "renovate/pytest-9.x", RC, {"uv.lock"}, True),
        ("main", "renovate/astral-sh-uv-0.x", RC, WORKFLOW, False),
        ("main", "renovate/quantinuum-packages", BETA, LOCK, False),
        ("main", "fix-blocking-issue", RC, LOCK, False),
        (
            "release/26.1",
            "renovate/release/26.1-quantinuum-patch-updates",
            RC,
            LOCK,
            False,
        ),
    ],
)
def test_holds_only_renovate_dependency_updates_to_main_during_rc(
    base, head, preview, files, blocked
):
    assert dependency_freeze.frozen(base, head, preview, lambda: files) is blocked


def test_changed_files_are_only_listed_for_a_candidate_update():
    files = Mock(side_effect=AssertionError("listed files"))
    assert not dependency_freeze.frozen("main", "fix-blocking-issue", RC, files)


def test_merge_queue_groups_resolve_the_queued_pr_branch(monkeypatch):
    client = Mock()
    client.pulls.get.return_value = {"head": {"ref": "renovate/quantinuum-packages"}}
    monkeypatch.setattr("github_api.create_client", lambda: client)
    event = {
        "merge_group": {
            "head_ref": "refs/heads/gh-readonly-queue/main/pr-42-0123456789abcdef"
        }
    }
    assert dependency_freeze.pull_request("merge_group", event) == (
        "main",
        "renovate/quantinuum-packages",
        42,
    )
    client.pulls.get.assert_called_once_with(pull_number=42)


@pytest.mark.parametrize(
    "channel,files,fails",
    [
        ("rc", ["uv.lock"], True),
        ("rc", [".github/workflows/ci.yml"], False),
        ("beta", ["uv.lock"], False),
    ],
)
def test_cli_reads_the_pull_request_event_preview_channel_and_files(
    tmp_path, monkeypatch, channel, files, fails
):
    root = tmp_path / "repo"
    (root / ".github").mkdir(parents=True)
    (root / ".github/preview.json").write_text(
        json.dumps({"target": "26.2.0", "channel": channel})
    )
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {
                "pull_request": {
                    "number": 7,
                    "base": {"ref": "main"},
                    "head": {"ref": "renovate/quantinuum-packages"},
                }
            }
        )
    )
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    client = Mock()
    client.pulls.list_files = lambda pull_number, page, per_page: (
        [{"filename": name} for name in files] if page == 1 else []
    )
    monkeypatch.setattr("github_api.create_client", lambda: client)
    script = root / "scripts/dependency_freeze.py"
    script.parent.mkdir()
    script.write_text(Path(dependency_freeze.__file__).read_text())
    if fails:
        with pytest.raises(SystemExit) as exit:
            runpy.run_path(str(script), run_name="__main__")
        assert exit.value.code == 1
    else:
        runpy.run_path(str(script), run_name="__main__")
