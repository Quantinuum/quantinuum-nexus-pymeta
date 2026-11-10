"""Check that repository uv commands isolate package index configuration."""

import os
from unittest.mock import patch
from uv_pypi import CONFIG, SOURCE_VARIABLES, run_uv


class TestPyPIIsolation:
    def test_overrides_are_removed_without_modifying_the_parent_environment(self):
        overrides = dict.fromkeys(SOURCE_VARIABLES, "https://private.example/simple")
        with patch.dict(os.environ, {**overrides, "UV_CACHE_DIR": "/tmp/cache"}):
            with patch("uv_pypi.subprocess.run") as run:
                run_uv("lock", "--check")
            (arguments,) = run.call_args.args
            assert arguments == ["uv", "--config-file", str(CONFIG), "lock", "--check"]
            environment = run.call_args.kwargs["env"]
            for variable in SOURCE_VARIABLES:
                if variable != "UV_CONFIG_FILE":
                    assert variable not in environment
            assert environment["UV_CONFIG_FILE"] == str(CONFIG)
            assert environment["UV_CACHE_DIR"] == "/tmp/cache"
            assert os.environ["UV_INDEX"] == overrides["UV_INDEX"]
