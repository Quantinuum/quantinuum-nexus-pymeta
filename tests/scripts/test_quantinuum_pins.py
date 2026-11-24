"""Check detection of unpinned Quantinuum packages without PyPI requests."""

import quantinuum_pins

QUANTINUUM = {"project_urls": {"Source": "https://github.com/Quantinuum/guppylang"}}
CQCL = {"project_urls": {"Repository": "https://github.com/CQCL/qnexus"}}
STAFF = {"project_urls": None, "author_email": "Dev <dev@quantinuum.com>"}
OTHER = {"project_urls": {"Source": "https://github.com/numpy/numpy"}}

LOCK = {
    "package": [
        {
            "name": "quantinuum-nexus",
            "version": "26.2.0",
            "dependencies": [{"name": "guppylang"}, {"name": "qnexus"}],
        },
        {
            "name": "guppylang",
            "version": "1.2.1",
            "dependencies": [
                {"name": "guppylang-internals"},
                {"name": "numpy"},
                {"name": "llvmlite", "version": "0.50.0"},
            ],
        },
        {"name": "guppylang-internals", "version": "1.2.1"},
        {
            "name": "qnexus",
            "version": "0.51.4",
            "optional-dependencies": {"wasm": [{"name": "qwasm"}]},
        },
        {"name": "qwasm", "version": "1.0.1"},
        {"name": "numpy", "version": "2.5.4"},
        {"name": "llvmlite", "version": "0.50.0"},
        {"name": "llvmlite", "version": "0.44.0", "dependencies": [{"name": "zixy"}]},
        {"name": "zixy", "version": "0.4.3"},
        {"name": "pytest", "version": "9.2.0"},
    ]
}
METADATA = {
    "guppylang": QUANTINUUM,
    "guppylang-internals": STAFF,
    "qnexus": CQCL,
    "qwasm": CQCL,
    "numpy": OTHER,
    "llvmlite": OTHER,
    "zixy": QUANTINUUM,
}


def test_walks_runtime_dependencies_extras_and_the_locked_version():
    assert quantinuum_pins.runtime_packages(LOCK, "quantinuum-nexus") == {
        ("guppylang", "1.2.1"),
        ("guppylang-internals", "1.2.1"),
        ("qnexus", "0.51.4"),
        ("qwasm", "1.0.1"),
        ("numpy", "2.5.4"),
        ("llvmlite", "0.50.0"),
    }


def test_reports_unpinned_quantinuum_packages_only():
    project = {
        "name": "quantinuum-nexus",
        "dependencies": ["guppylang==1.2.1", "Qnexus==0.51.4", "numpy>=2"],
    }
    seen = []

    def info(name, version):
        seen.append((name, version))
        return METADATA[name]

    assert quantinuum_pins.unpinned(project, LOCK, info) == [
        ("guppylang-internals", "1.2.1"),
        ("qwasm", "1.0.1"),
    ]
    assert ("guppylang-internals", "1.2.1") in seen


def test_identifies_quantinuum_packages_from_links_and_people():
    assert quantinuum_pins.is_quantinuum(QUANTINUUM)
    assert quantinuum_pins.is_quantinuum(CQCL)
    assert quantinuum_pins.is_quantinuum(STAFF)
    assert quantinuum_pins.is_quantinuum({"home_page": "https://github.com/cqcl"})
    assert not quantinuum_pins.is_quantinuum(OTHER)
    assert not quantinuum_pins.is_quantinuum(
        {"project_urls": {"Fork": "https://github.com/CQCL-fork/tool"}}
    )
    assert not quantinuum_pins.is_quantinuum({})


def test_readme_must_list_exactly_the_pinned_packages():
    project = {"dependencies": ["guppylang==1.2.1", "Qwasm==1.0.1", "numpy>=2"]}
    readme = "\n".join(
        [
            "# SDK",
            "Installs `quantinuum-nexus`.",
            "## Included tools",
            "| Guppy | `guppylang` | Write programs. |",
            "Packages use `uv` and need `numpy`.",
            "### Supporting packages",
            "- `hugr`",
            "## Installation",
            "Run `uv add quantinuum-nexus` to use `qwasm`.",
        ]
    )
    assert quantinuum_pins.readme_mismatches(project, readme) == (
        ["qwasm"],
        ["hugr"],
    )
