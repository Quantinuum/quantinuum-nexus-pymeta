"""Run uv with this repository's PyPI configuration and no index overrides."""

import os
import subprocess
import sys
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "uv.toml"
SOURCE_VARIABLES = (
    "UV_CONFIG_FILE",
    "UV_NO_CONFIG",
    "UV_INDEX",
    "UV_DEFAULT_INDEX",
    "UV_INDEX_URL",
    "UV_EXTRA_INDEX_URL",
    "UV_FIND_LINKS",
    "UV_NO_INDEX",
    "UV_PUBLISH_URL",
    "UV_PUBLISH_INDEX",
)


def run_uv(*arguments: str) -> None:
    environment = os.environ.copy()
    for variable in SOURCE_VARIABLES:
        environment.pop(variable, None)
    # Build subprocesses must use the same configuration.
    environment["UV_CONFIG_FILE"] = str(CONFIG)
    subprocess.run(
        ["uv", "--config-file", str(CONFIG), *arguments],
        env=environment,
        check=True,
    )


if __name__ == "__main__":
    try:
        run_uv(*sys.argv[1:])
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
