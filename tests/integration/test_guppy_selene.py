"""Guppy programs compiled to HUGR and run on the Selene emulator."""

from guppylang import guppy
from guppylang.std.builtins import array, output
from guppylang.std.quantum import (
    collect_measurements,
    cx,
    h,
    measure,
    measure_array,
    qubit,
    t,
    tdg,
)
from hugr.package import Package
from hugr.qsystem.result import QsysResult
from pytket.backends.backendresult import BackendResult
from selene_sim import DepolarizingErrorModel, Quest, Stim


@guppy
def ghz() -> None:
    qs = array(qubit() for _ in range(3))
    h(qs[0])
    for i in range(2):
        cx(qs[i], qs[i + 1])
    output("ghz", collect_measurements(measure_array(qs)))


@guppy
def non_clifford_identity() -> None:
    q = qubit()
    h(q)
    t(q)
    tdg(q)
    h(q)
    output("q", measure(q).read())


def test_ghz_on_stabilizer_and_statevector_simulators(emulate, register_outcomes):
    for stabilizer in [True, False]:
        result = emulate(ghz, n_qubits=3, shots=50, stabilizer=stabilizer)
        assert register_outcomes(result, "ghz") == {"000", "111"}


def test_non_clifford_program_runs_on_statevector(emulate, register_outcomes):
    result = emulate(non_clifford_identity, n_qubits=1, stabilizer=False)
    assert register_outcomes(result, "q") == {"0"}


def test_serialized_hugr_runs_directly_on_selene(selene_build):
    package = Package.from_bytes(ghz.compile().to_bytes())
    runner = selene_build(package)
    for simulator in [Stim(random_seed=1), Quest(random_seed=1)]:
        result = QsysResult(runner.run_shots(simulator, n_qubits=3, n_shots=50))
        counts = result.register_counts()["ghz"]
        assert counts.total() == 50
        assert set(counts) == {"000", "111"}


def test_error_model_introduces_noise(selene_build):
    noise = DepolarizingErrorModel(random_seed=1, p_init=0.2, p_meas=0.2)
    result = QsysResult(
        selene_build(ghz.compile()).run_shots(
            Stim(random_seed=1), error_model=noise, n_qubits=3, n_shots=100
        )
    )
    counts = result.register_counts()["ghz"]
    assert counts.total() == 100
    assert set(counts) - {"000", "111"}


def test_emulator_results_convert_to_pytket(emulate):
    result = emulate(ghz, n_qubits=3)
    backend_result = result.to_pytket()
    assert isinstance(backend_result, BackendResult)
    assert set(backend_result.get_counts()) == {(0, 0, 0), (1, 1, 1)}
