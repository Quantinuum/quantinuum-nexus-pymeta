"""Check the RC dependency freeze gate without making GitHub requests."""

import json
import runpy
from pathlib import Path
from unittest.mock import Mock

import pytest

import dependency_freeze

BETA = {"target": "26.2.0", "channel": "beta"}
RC = {"target": "26.2.0", "channel": "rc"}


@pytest.mark.parametrize(
    "base,head,preview,blocked",
    [
        ("main", "renovate/quantinuum-packages", RC, True),
        ("main", "renovate/quantinuum-packages", BETA, False),
        ("main", "fix-blocking-issue", RC, False),
        ("release/26.1", "renovate/release/26.1-quantinuum-patch-updates", RC, False),
    ],
)
def test_holds_only_renovate_updates_to_main_during_rc(base, head, preview, blocked):
    assert dependency_freeze.frozen(base, head, preview) is blocked


def test_merge_queue_groups_resolve_the_queued_pr_branch(monkeypatch):
    client = Mock()
    client.pulls.get.return_value = {"head": {"ref": "renovate/quantinuum-packages"}}
    monkeypatch.setattr("github_api.create_client", lambda: client)
    event = {
        "merge_group": {
            "head_ref": "refs/heads/gh-readonly-queue/main/pr-42-0123456789abcdef"
        }
    }
    assert dependency_freeze.pull_request_branches("merge_group", event) == (
        "main",
        "renovate/quantinuum-packages",
    )
    client.pulls.get.assert_called_once_with(pull_number=42)


@pytest.mark.parametrize("channel,fails", [("rc", True), ("beta", False)])
def test_cli_reads_the_pull_request_event_and_preview_channel(
    tmp_path, monkeypatch, channel, fails
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
                    "base": {"ref": "main"},
                    "head": {"ref": "renovate/quantinuum-packages"},
                }
            }
        )
    )
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    script = root / "scripts/dependency_freeze.py"
    script.parent.mkdir()
    script.write_text(Path(dependency_freeze.__file__).read_text())
    if fails:
        with pytest.raises(SystemExit) as exit:
            runpy.run_path(str(script), run_name="__main__")
        assert exit.value.code == 1
    else:
        runpy.run_path(str(script), run_name="__main__")
