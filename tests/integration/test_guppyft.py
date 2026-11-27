"""Guppy programs encoded with guppyft's Steane code and run on Selene."""

import pytest
from guppyft.code.steane.encode import SteaneBuilder
from guppylang import guppy
from guppylang.std.builtins import output
from guppylang.std.quantum import cx, h, measure, qubit, x, z
from hugr.package import Package
from hugr_qir.hugr_to_qir import hugr_to_qir


@guppy
def teleport_one() -> None:
    src = qubit()
    x(src)
    tmp = qubit()
    tgt = qubit()
    h(tmp)
    cx(tmp, tgt)
    cx(src, tmp)
    h(src)
    if measure(src).read():
        z(tgt)
    if measure(tmp).read():
        x(tgt)
    output("tgt", measure(tgt).read())


def test_steane_encoded_teleportation_emulates_logically(build_emulator):
    steane = SteaneBuilder.new(n_blocks=3).build()
    encoded = steane.encode(teleport_one.compile())
    assert isinstance(encoded, Package)

    # Three logical blocks of 7 physical qubits, plus ancillas for syndrome
    # extraction.
    result = (
        build_emulator(encoded, n_qubits=30)
        .stabilizer_sim()
        .with_seed(3)
        .with_shots(10)
        .run()
    )
    assert result.register_counts()["tgt"] == {"1": 10}


@pytest.mark.xfail(
    strict=True,
    raises=ValueError,
    reason=(
        "reports/2026-11-27-sdk-integration.md#4: "
        "hugr-qir fails to emit LLVM for guppyft-encoded programs"
    ),
)
def test_steane_encoded_program_lowers_to_qir():
    steane = SteaneBuilder.new(n_blocks=3).build()
    hugr_to_qir(steane.encode(teleport_one.compile()))
