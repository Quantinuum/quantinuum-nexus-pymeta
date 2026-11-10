"""Run pytest matrices and pre-commit with the repository's pinned tools."""

import argparse
import os
from pathlib import Path
import tomllib

from python_matrix import supported_versions
from uv_pypi import run_uv

ROOT = Path(__file__).resolve().parents[1]


def tool_requirement(name: str) -> str:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    return next(
        requirement
        for group in config["dependency-groups"].values()
        for requirement in group
        if isinstance(requirement, str) and requirement.startswith(name + "==")
    )


def run_tests(kind: str, version: str):
    supported = supported_versions()
    if version != "all" and version not in supported:
        raise ValueError(
            f"Choose all or a supported Python version: {', '.join(supported)}"
        )
    for selected in supported if version == "all" else [version]:
        print(f"Running {kind} tests on Python {selected}", flush=True)
        run_uv(
            "run",
            "--no-project",
            "--isolated",
            "--python",
            selected,
            "--with",
            tool_requirement("pytest"),
            *(["--with", tool_requirement("ghapi")] if kind == "scripts" else []),
            "python",
            "-m",
            "pytest",
            "-q",
            f"tests/{kind}",
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for kind in ["scripts", "package"]:
        commands.add_parser(kind).add_argument("version", nargs="?", default="all")
    commands.add_parser("hooks-install")
    commands.add_parser("hooks").add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    os.chdir(ROOT)
    if args.command in ["scripts", "package"]:
        run_tests(args.command, args.version)
    elif args.command == "hooks-install":
        os.environ.pop("VIRTUAL_ENV", None)
        run_uv("run", "--locked", "--python", "3.12", "pre-commit", "install")
    else:
        os.environ.pop("VIRTUAL_ENV", None)
        arguments = (
            args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        )
        run_uv(
            "run",
            "--locked",
            "--python",
            "3.12",
            "pre-commit",
            "run",
            *(arguments or ["--all-files"]),
        )
