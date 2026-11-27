"""Shared fixtures for SDK integration tests.

These tests import the SDK components, so they run in the locked project
environment: ``python scripts/tasks.py integration`` or ``just test-integration``.
"""

import pytest
import selene_sim
from guppylang.emulator import EmulatorBuilder


@pytest.fixture(scope="session")
def selene_build(tmp_path_factory):
    """Build a HUGR package into a Selene runner inside pytest's temp directory.

    Selene otherwise leaves every build in a new system temporary directory.
    """

    def build(package):
        return selene_sim.build(package, build_dir=tmp_path_factory.mktemp("selene"))

    return build


@pytest.fixture(scope="session")
def build_emulator(tmp_path_factory):
    """Build a HUGR package into a Guppy emulator inside pytest's temp directory."""

    def build(package, n_qubits):
        builder = EmulatorBuilder().with_build_dir(tmp_path_factory.mktemp("selene"))
        return builder.build(package, n_qubits=n_qubits)

    return build


@pytest.fixture(scope="session")
def emulate(build_emulator):
    """Run a Guppy entrypoint on the Selene emulator and return the result.

    Stim is the default because Clifford programs are fast and deterministic for
    a given seed; pass ``stabilizer=False`` to use the statevector simulator.
    Each entrypoint is compiled and built once per session.
    """
    emulators = {}

    def run(entrypoint, n_qubits, shots=20, *, stabilizer=True, seed=1):
        key = (id(entrypoint), n_qubits)
        if key not in emulators:
            emulators[key] = build_emulator(entrypoint.compile(), n_qubits)
        emulator = emulators[key]
        if stabilizer:
            emulator = emulator.stabilizer_sim()
        return emulator.with_seed(seed).with_shots(shots).run()

    return run


def outcomes(result, register):
    """Return the distinct bitstrings recorded for one output register."""
    return set(result.register_counts()[register])


@pytest.fixture(scope="session")
def register_outcomes():
    return outcomes
