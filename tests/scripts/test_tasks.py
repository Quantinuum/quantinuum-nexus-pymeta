"""Check that local test commands use the supported matrix and pinned tools."""

from unittest.mock import Mock

import pytest

import tasks
from python_matrix import python_versions


@pytest.mark.parametrize(
    "specifier,expected",
    [
        (">=3.12,<3.15", ["3.12", "3.13", "3.14"]),
        (">=3.13, <3.15", ["3.13", "3.14"]),
    ],
)
def test_bounded_python_matrix_does_not_need_network(specifier, expected, monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        Mock(side_effect=AssertionError("Unexpected network call")),
    )
    assert python_versions(specifier) == expected


@pytest.mark.parametrize("kind", ["scripts", "package"])
def test_test_commands_use_each_supported_interpreter_and_the_locked_dev_group(
    kind, monkeypatch
):
    run = Mock()
    monkeypatch.setattr(tasks, "supported_versions", lambda: ["3.12", "3.13", "3.14"])
    monkeypatch.setattr(tasks, "run_uv", run)
    tasks.run_tests(kind, ["all"])
    calls = [call.args for call in run.call_args_list]
    assert [call[call.index("--python") + 1] for call in calls] == [
        "3.12",
        "3.13",
        "3.14",
    ]
    assert all("--isolated" in call and "--locked" in call for call in calls)
    assert all(call[call.index("--only-group") + 1] == "dev" for call in calls)
    assert not any("--with" in call for call in calls)
    assert all(call[-1] == f"tests/{kind}" for call in calls)


def test_unsupported_python_version_fails_before_running_tests(monkeypatch):
    run = Mock()
    monkeypatch.setattr(tasks, "supported_versions", lambda: ["3.12", "3.13", "3.14"])
    monkeypatch.setattr(tasks, "run_uv", run)
    with pytest.raises(ValueError, match="supported Python version"):
        tasks.run_tests("scripts", ["3.12", "3.11"])
    run.assert_not_called()


def test_selected_versions_run_once_in_the_given_order(monkeypatch):
    run = Mock()
    monkeypatch.setattr(tasks, "supported_versions", lambda: ["3.12", "3.13", "3.14"])
    monkeypatch.setattr(tasks, "run_uv", run)
    tasks.run_tests("package", ["3.14", "3.12", "3.14"])
    calls = [call.args for call in run.call_args_list]
    assert [call[call.index("--python") + 1] for call in calls] == ["3.14", "3.12"]
