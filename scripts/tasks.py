"""Run pytest matrices and pre-commit with the repository's pinned tools."""

import argparse
import os
import subprocess
from pathlib import Path

from python_matrix import supported_versions

ROOT = Path(__file__).resolve().parents[1]
# Keep in sync with the hook entries in .pre-commit-config.yaml. Installing only
# the dev group avoids building the project, whose build backend is not locked.
HOOK_RUN = ("run", "--locked", "--only-group", "dev", "--python", "3.12")


def run_uv(*arguments: str) -> None:
    subprocess.run(["uv", *arguments], check=True)


def run_tests(kind: str, versions: list[str]):
    supported = supported_versions()
    selected_versions = (
        supported if versions == ["all"] else list(dict.fromkeys(versions))
    )
    if any(version not in supported for version in selected_versions):
        raise ValueError(
            f"Choose all or supported Python versions: {', '.join(supported)}"
        )
    for selected in selected_versions:
        print(f"Running {kind} tests on Python {selected}", flush=True)
        # The locked dev group provides pytest without the runtime dependencies.
        run_uv(
            "run",
            "--isolated",
            "--locked",
            "--only-group",
            "dev",
            "--python",
            selected,
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
        commands.add_parser(kind).add_argument("versions", nargs="*", default=["all"])
    commands.add_parser("hooks-install")
    commands.add_parser("hooks").add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    os.chdir(ROOT)
    if args.command in ["scripts", "package"]:
        run_tests(args.command, args.versions)
    elif args.command == "hooks-install":
        os.environ.pop("VIRTUAL_ENV", None)
        run_uv(*HOOK_RUN, "pre-commit", "install")
    else:
        os.environ.pop("VIRTUAL_ENV", None)
        arguments = (
            args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        )
        run_uv(*HOOK_RUN, "pre-commit", "run", *(arguments or ["--all-files"]))
