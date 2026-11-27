set windows-shell := ["powershell.exe", "-NoProfile", "-Command"]

# Resolve packages only from PyPI: use uv.toml in place of user- and system-level
# configuration, and ignore index overrides from the environment.
export UV_CONFIG_FILE := justfile_directory() / "uv.toml"
unexport UV_NO_CONFIG
unexport UV_INDEX
unexport UV_DEFAULT_INDEX
unexport UV_INDEX_URL
unexport UV_EXTRA_INDEX_URL
unexport UV_FIND_LINKS
unexport UV_NO_INDEX
unexport UV_INDEX_STRATEGY
unexport UV_PUBLISH_URL
unexport UV_PUBLISH_INDEX

tasks := "uv run --no-project --isolated --python 3.12 python scripts/tasks.py"

# List available commands.
default:
    @just --list

# Install pinned development tools and activate the commit hooks.
setup: hooks-install

# Check the lockfile and test repository scripts on every supported Python.
test: check-lock test-scripts

# Test repository scripts on all supported Python versions or one minor.
test-scripts version="all":
    {{tasks}} scripts "{{version}}"

# Test package installation on all supported Python versions or one minor.
test-package version="all":
    {{tasks}} package "{{version}}"

# Run pytest without the distribution installation tests; choose all or one minor.
test-python version="all":
    @just test-scripts "{{version}}"

# Build and install both distributions on all supported Python versions or one minor.
test-install version="all":
    @just test-package "{{version}}"

# Run all tests, including fresh distribution installations.
test-all: test test-package

# Verify that dependency metadata matches uv.lock.
check-lock:
    uv lock --check

# Update uv.lock from PyPI; optional arguments are forwarded to uv lock.
lock *args:
    uv lock {{args}}

# Require exact pins, listed in the README, for every Quantinuum package (queries PyPI).
check-pins:
    uv run --no-project --isolated --python 3.12 python scripts/quantinuum_pins.py

# Install the Git pre-commit hook using the persistent project environment.
hooks-install:
    {{tasks}} hooks-install

# Run commit checks; optional arguments are forwarded to pre-commit run.
hooks *args:
    {{tasks}} hooks -- {{args}}
