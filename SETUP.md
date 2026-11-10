# Development and repository setup

This guide covers local development and the one-time configuration needed to
operate this repository. To install the published SDK for use in your own
project, see the [README](README.md#installation).

## Local development and validation

Install Python, uv 0.13.5, `just`, and Git, then run:

```sh
just setup                 # Install pinned dev tools and activate commit hooks
just test                  # Lockfile and script tests on 3.12/3.13/3.14
just test-scripts 3.13      # Script tests on one supported Python version
just test-package          # Fresh wheel and source installs on 3.12/3.13/3.14
just test-package 3.12      # Package tests on one Python version
just test-all              # All tests, including the installation matrix
just hooks                 # Run the pre-commit checks over all tracked files
```

`just` lists the available commands. Python versions come from `requires-python`
in `pyproject.toml`, shared by the local runner and CI. The bounded range is
enumerated without a network request; an unbounded range uses GitHub's stable
Python version manifest. uv downloads missing interpreters when needed.

Python tests use pytest, with exact pytest and pre-commit versions pinned in the
`dev` dependency group. The runner isolates pytest from the runtime dependencies
and runs each Python minor sequentially. Tests are separated by what they check:

- `tests/scripts/` checks repository tooling, including release and merge policies.
- `tests/package/` checks the metapackage itself, currently wheel and source installation.

An ordinary `pytest` run selects `tests/scripts/`. Use `pytest tests/package` to
select package tests or `pytest tests` to run both suites on the current Python.
The `just` commands run the selected suite across supported Python versions.

`just setup` installs a Git pre-commit hook in this checkout. The hooks run
Ruff's linter with safe automatic fixes, format Python files, trim trailing
whitespace, ensure a single final newline, and normalize text line endings to
LF. Markdown hard line breaks are preserved. Hook tool versions are pinned in
`.pre-commit-config.yaml`; pre-commit installs them in isolated environments.
If a hook modifies files, review and stage the changes before committing again.

To lint or format every tracked Python file explicitly, run:

```sh
just hooks ruff-check --all-files
just hooks ruff-format --all-files
```

On commits that change Python code or relevant configuration, the hook runs
pytest on every supported Python minor, including approval, merge, and
publication policy tests.
Dependency changes also check the lockfile. Documentation-only commits skip these
tests. The Python suite includes temporary Git repositories, so a full commit
check can take about a minute. Distribution installation tests run in CI and
through `just test-package` or `just test-all`.

Hooks must be installed once per clone. The pre-commit executable lives in the
persistent project `.venv`; run `just setup` again after recreating it. The test
repositories disable Git hooks to avoid recursive test runs during commits.

The approval, merge, and release workflows use `ghapi` with their GitHub App or
job tokens. Its exact version is pinned in the `automation` dependency group,
which is also included in `dev`. Git operations use the Git executable.
Tests mock GitHub responses and never submit real reviews or merges.

To run an automation script locally, set `GITHUB_REPOSITORY` to `owner/repository`
and `GH_TOKEN` to a token with the required permissions, then use
`python3 scripts/uv_pypi.py run --isolated --locked --only-group automation python scripts/<script>.py ...`.
The automation dependencies are excluded from the published SDK's runtime dependencies.

`scripts/uv_pypi.py` uses `uv.toml` explicitly, which excludes user- and
system-level uv configuration. It also removes package-index environment
overrides for the child process. Installation tests and CI use this same PyPI
configuration, without changing your global settings.

Use this wrapper for repository uv commands, including installing from this
checkout:

```sh
python3 scripts/uv_pypi.py pip install .
```

Bare `uv` commands still merge user-level index configuration. For an explicit
configuration without the wrapper, use `uv --config-file uv.toml ...`; environment
overrides still apply to that form. A published metapackage cannot control the
installer's indexes. For the published uv installation command in the [README](README.md#installation), unset
`UV_INDEX`, `UV_EXTRA_INDEX_URL`, and `UV_FIND_LINKS` if they are set.

The installation tests build a wheel and source distribution, install each
into a separate fresh environment, run `uv pip check`, and verify the installed
metapackage metadata and all six dependency versions. They resolve dependencies
as a consumer would, independently of the development lockfile.

GitHub CI checks the lockfile and both installation formats on every stable
CPython minor version in the declared Python range. It uses `ubuntu-latest`,
`windows-latest`, `macos-latest` (Apple Silicon), and `macos-26-intel` (the latest
standard Intel macOS image), excluding the unsupported Intel macOS/Python 3.14
combination. The explicit Intel label needs updating when GitHub
introduces a newer image. CI uses the same pytest runner as the just recipes,
running the script and package suites separately on each matrix cell.

## One-time repository setup

1. Create the GitHub repository, add its remote, and push an initial `feat:`
   commit to `main`. Enable GitHub Actions, Dependabot, and squash merges.
2. Create and install a GitHub App on this repository with Contents, Pull
   requests, and Issues read/write permissions, plus Actions read permission
   for RC promotion validation. Set the Actions variable
   `RELEASE_APP_CLIENT_ID` and secret `RELEASE_APP_PRIVATE_KEY`. Release and merge
   automation remain disabled until the client ID is configured. App tokens
   ensure bot-created PRs, merges, and releases trigger subsequent workflows.
3. Protect `main`: require the `Installation checks` status and require branches
   to be up to date before merging. Do not grant the release App a protection
   bypass. If reviews are required for every PR, a person must approve bot PRs;
   unattended updates need repository rules that permit them after the required
   checks pass.
4. On PyPI, configure a trusted publisher (or pending publisher for a new
   project) for `quantinuum-nexus-sdk`, your GitHub owner/repository,
   workflow `publish.yml`, and environment `pypi`. Create that GitHub environment;
   leave required reviewers unset for unattended publication. Package name
   availability and organization ownership must be confirmed before publishing.
5. Push the initial commit or dispatch Release Please. It creates the first
   release PR; passing CI starts the automated release chain.

The workflows honor repository protections. No hosted CI run or PyPI publication
occurs until the repository is pushed and these credentials are configured.

For dependency updates, preview releases, release series promotion, and publication
retries, see [Maintaining and releasing](MAINTAINING.md).
