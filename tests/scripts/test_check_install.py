"""Check that installation checks resolve packages only from PyPI."""

import os
from unittest.mock import Mock

import check_install


def test_commands_ignore_uv_configuration_and_index_overrides(monkeypatch):
    for variable in check_install.SOURCE_VARIABLES:
        monkeypatch.setenv(variable, "https://private.example/simple")
    monkeypatch.setenv("UV_NO_CONFIG", "0")
    run = Mock()
    monkeypatch.setattr("subprocess.run", run)

    check_install.run("uv", "build")

    environment = run.call_args.kwargs["env"]
    assert environment["UV_NO_CONFIG"] == "1"
    assert not set(check_install.SOURCE_VARIABLES) & set(environment)
    assert os.environ["UV_INDEX"] == "https://private.example/simple"
