"""Build both distributions and pylock.toml, and install each in isolated environments."""

import argparse
import importlib.metadata
import os
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# These checks resolve packages afresh rather than from uv.lock, so they enforce
# the repository's PyPI-only configuration however the script is launched.
# Keep in sync with the unexported variables in the justfile.
SOURCE_VARIABLES = (
    "UV_ENV_FILE",
    "UV_NO_CONFIG",
    "UV_INDEX",
    "UV_DEFAULT_INDEX",
    "UV_INDEX_URL",
    "UV_EXTRA_INDEX_URL",
    "UV_FIND_LINKS",
    "UV_NO_INDEX",
    "UV_INDEX_STRATEGY",
    "UV_PUBLISH_URL",
    "UV_PUBLISH_INDEX",
)


def check_installed() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    distribution = importlib.metadata.distribution(project["name"])
    assert distribution.version == project["version"]
    assert set(distribution.metadata["Requires-Python"].split(",")) == set(
        project["requires-python"].split(",")
    )
    expected = {requirement.lower() for requirement in project["dependencies"]}
    actual = {requirement.lower() for requirement in distribution.requires or []}
    assert actual == expected, (actual, expected)
    for requirement in project["dependencies"]:
        name, version = requirement.split("==")
        assert "*" not in version, requirement
        installed = importlib.metadata.version(name)
        assert installed == version, (name, installed, version)
    print(f"Verified {project['name']}=={distribution.version} on {sys.version}")


def run(*command: str) -> None:
    environment = {
        name: value
        for name, value in os.environ.items()
        if name not in SOURCE_VARIABLES
    }
    environment["UV_CONFIG_FILE"] = str(ROOT / "uv.toml")
    subprocess.run(command, cwd=ROOT, env=environment, check=True)


def check_distributions() -> None:
    run("uv", "build", "--clear")
    dist = ROOT / "dist"
    wheels, sources = sorted(dist.glob("*.whl")), sorted(dist.glob("*.tar.gz"))
    assert len(wheels) == 1 and len(sources) == 1, (wheels, sources)
    lock = dist / "pylock.toml"
    # Keep in sync with the release asset export in publish.yml.
    run(
        "uv",
        "export",
        "--locked",
        "--format",
        "pylock.toml",
        "--no-header",
        "--no-default-groups",
        "--no-emit-project",
        "-o",
        str(lock),
    )
    installations = [
        [[str(wheels[0])]],
        [[str(sources[0])]],
        # pylock.toml cannot be combined with other requirements in one command.
        [["-r", str(lock)], ["--no-deps", str(wheels[0])]],
    ]
    for steps in installations:
        with tempfile.TemporaryDirectory(prefix="nexus-install-") as temporary:
            environment = Path(temporary) / "venv"
            python = environment / (
                "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
            )
            run("uv", "venv", "--python", sys.executable, str(environment))
            for arguments in steps:
                run("uv", "pip", "install", "--python", str(python), *arguments)
            run("uv", "pip", "check", "--python", str(python))
            run(str(python), str(Path(__file__).resolve()), "--check")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    if parser.parse_args().check:
        check_installed()
    else:
        check_distributions()
