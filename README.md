# Quantinuum Nexus Python Metapackage

`quantinuum-nexus` installs a versioned set of Quantinuum's Python tools for
quantum programming, fault tolerance, local emulation, circuit compilation, and
access to Quantinuum Nexus. Install one SDK version to select the exact component
versions for that release instead of choosing each component version separately.

This is a Python **metapackage**: it contains dependency metadata, with no
additional Python API. After installation, use each component's own imports,
APIs, and documentation.

## Included tools

The SDK includes these six packages:

| Tool | Python package | Purpose |
| --- | --- | --- |
| Guppy | `guppylang` | Write hybrid quantum-classical programs in a language embedded in Python. |
| Guppy FT | `guppyft` | Write, compile, and run fault-tolerant Guppy programs. |
| Guppy Algorithms | `guppyalgos` | Work with quantum algorithms in the Guppy toolkit. |
| Selene | `selene-sim` | Emulate hybrid quantum-classical programs locally. |
| TKET | `pytket` | Build, transform, and optimize quantum circuits. |
| Nexus client | `qnexus` | Access the Quantinuum Nexus platform from Python. |

### Supporting packages

The tools above depend on further Quantinuum packages. The SDK installs these
automatically and pins them as well, so each release identifies one exact
version of all Quantinuum code. You rarely need to use them directly:

- `guppylang-internals`
- `hugr`
- `quantinuum-schemas`
- `qwasm`
- `selene-core`
- `selene-formats`
- `selene-hugr-qis-compiler`
- `tket`
- `tket-eccs`
- `tket-exts`
- `zixy`

See the [Quantinuum documentation](https://docs.quantinuum.com/) for tutorials
and API references, and the
[platform release notes](https://docs.quantinuum.com/platform/releases/) for
component release notes and platform changes.

## Python and platform support

This release supports CPython 3.12, 3.13, and 3.14 on Linux, Windows, and macOS,
with one exception: **Python 3.14 is not supported on Intel macOS**. On Intel
Macs, use Python 3.12 or 3.13. This restriction also applies to an Intel Python
interpreter running through Rosetta on an Apple Silicon Mac; use a native ARM64
interpreter for Python 3.14.

To limit CI usage, each change is installation-tested on every platform with
the oldest and newest supported Python versions (3.12 and 3.14, or 3.12 and 3.13
on Intel macOS). Python 3.13 on the other platforms is supported, but tested
through the full local installation tests rather than on every change.

Python 3.15 and later are outside this release's supported range. The pinned
`guppyalgos` version requires Python below 3.15.

## Installation

Add the SDK from PyPI to your uv project using:

```sh
uv add quantinuum-nexus
```

Or install it into an existing activated virtual environment using:

```sh
uv pip install quantinuum-nexus
```

Alternatively, install it into that environment using pip:

```sh
python -m pip install quantinuum-nexus
```

Verify that the environment's installed dependencies are consistent with:

```sh
python -m pip check
```

There is no `quantinuum_nexus` module to import. Use the installed tools
directly, for example:

```python
from pytket import Circuit

circuit = Circuit(2).H(0).CX(0, 1)
```

### Installing from GitHub Releases

Each release is also available from
[GitHub Releases](https://github.com/Quantinuum/quantinuum-nexus-pymeta/releases).
Download the wheel (`.whl`) attached to the release you want. In a directory
containing that single SDK wheel, add it to your uv project using:

```sh
uv add ./quantinuum_nexus-*.whl
```

Or install it into an existing activated virtual environment using:

```sh
uv pip install ./quantinuum_nexus-*.whl
```

Alternatively, use pip:

```sh
python -m pip install ./quantinuum_nexus-*.whl
```

These shell examples expand the wheel filename; you can also pass its exact
path. Dependencies are resolved from PyPI as usual. A GitHub release is ready
to install once its wheel, source distribution, and `pylock.toml` appear under
release assets.

### Dependency versions and reproducibility

Each SDK release pins every Quantinuum package it installs to an exact version:
the six tools and the supporting packages listed
[above](#supporting-packages). Updating the SDK version is required to get
new component versions, because a component's independent release does not
change an already published SDK release.

Third-party dependencies, such as `numpy`, use compatible ranges so the SDK can
share an environment with your other packages. To reproduce the exact
environment a release was tested with, each GitHub release also attaches a
[`pylock.toml`](https://packaging.python.org/en/latest/specifications/pylock-toml/)
lock file. Install it with uv into a fresh virtual environment, then add the SDK
wheel without resolving dependencies again:

```sh
uv pip install -r pylock.toml
uv pip install --no-deps ./quantinuum_nexus-*.whl
```

The lock file covers the supported Python versions and platforms. It cannot be
combined with other requirements in a single install command.

## Release cycle

SDK versions follow **`YY.SERIES.PATCH`** calendar versioning:

- **YY** is the two-digit year the release series begins, such as `26` for 2026.
- **SERIES** starts at 1 each year and increases for each new release series.
- **PATCH** starts at 0 and increases for compatible updates within a series.

New release series are published as needed, with no fixed schedule or annual
limit. The series number indicates release order within the year. Patches to an
existing series retain its year and series number, even when published in a
later year.

### Stable release series and patches

New release series may introduce breaking component changes. Review the release
notes and validate your application before moving to a new series.

Patch releases within a series are intended to preserve compatibility. Automated
dependency updates propose eligible Quantinuum package updates for stable
series: minor and patch updates for packages at version 1.0 or later, and patch
updates only for packages below 1.0. Major updates and pre-1.0 minor updates are
reserved for the upcoming series. Not every dependency update produces a new SDK
release immediately.

[Supporting packages](#supporting-packages) are an exception. A component's
patch or minor update may require a breaking update of a supporting package: a
new major version, or a new minor version below 1.0. To deliver such component
updates within a series, maintainers may include these supporting package
updates in a reviewed SDK patch release. If your code uses a supporting package
directly, check the release notes before upgrading within a series.

For the two most recent stable series, patch updates and their SDK patch
releases merge automatically after CI. Minor updates require human review of
both the dependency PR and the resulting SDK patch release PR. Older series can
receive manually initiated patches. Stable patches can continue while the next
series is in preview.

### Betas and release candidates

Upcoming release series are offered as opt-in prereleases:

- **Beta** (`YY.SERIES.0bN`): a preview whose component versions can still
  change, including potentially breaking updates. Further previews increment
  the beta number.
- **Release candidate** (`YY.SERIES.0rcN`): the intended final component
  set, frozen except for reviewed fixes to blocking issues. Further fixes
  produce additional numbered release candidates.
- **Stable** (`YY.SERIES.0`): the first stable release in a series, using the
  chosen release candidate's exact direct dependency pins.

To try a preview, allow preview versions when adding or upgrading the SDK in
your uv project:

```sh
uv add --upgrade --prerelease allow quantinuum-nexus
```

Alternatively, use pip in an existing activated virtual environment:

```sh
python -m pip install --upgrade --pre quantinuum-nexus
```

## Repository guides

- [Development and repository setup](SETUP.md): local tools, validation commands,
  commit hooks, and one-time GitHub and PyPI configuration.
- [Maintaining and releasing](MAINTAINING.md): dependency updates, release
  workflows, beta and RC management, release series promotion, and publication retries.
