"""Shared fixtures for SDK integration tests.

These tests import the SDK components, so they run in the locked project
environment: ``python scripts/tasks.py integration`` or ``just test-integration``.
"""

import pytest


@pytest.fixture(scope="session")
def emulate():
    """Run a Guppy entrypoint on the Selene emulator and return the result.

    Stim is the default because Clifford programs are fast and deterministic for
    a given seed; pass ``stabilizer=False`` to use the statevector simulator.
    """

    def run(entrypoint, n_qubits, shots=20, *, stabilizer=True, seed=1):
        emulator = entrypoint.emulator(n_qubits=n_qubits)
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
