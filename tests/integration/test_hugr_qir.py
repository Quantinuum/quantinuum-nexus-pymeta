"""Guppy and pytket programs lowered to QIR with hugr-qir and checked by qircheck."""

import pytest
from guppylang import guppy
from guppylang.std.builtins import array, output, owned
from guppylang.std.quantum import (
    cx,
    discard_array,
    h,
    measure,
    qubit,
    x,
    z,
)
from hugr.package import Package
from hugr_qir.guppy_to_qir import guppy_to_qir_str
from hugr_qir.hugr_to_qir import hugr_to_qir
from hugr_qir.output import OutputFormat
from pytket import Circuit
from quantinuum_qircheck import qircheck


@guppy
def teleport(src: qubit @ owned, tgt: qubit) -> None:
    tmp = qubit()
    h(tmp)
    cx(tmp, tgt)
    cx(src, tmp)
    h(src)
    if measure(src).read():
        z(tgt)
    if measure(tmp).read():
        x(tgt)


@guppy
def teleport_one() -> None:
    src = qubit()
    x(src)
    tgt = qubit()
    teleport(src, tgt)
    output("tgt", measure(tgt).read())


ghz_circuit = guppy.load_pytket(
    "ghz_circuit",
    Circuit(3).H(0).CX(0, 1).CX(1, 2).measure_all(),
    use_arrays=True,
)


@guppy
def run_ghz_circuit() -> None:
    qs = array(qubit() for _ in range(3))
    bits = ghz_circuit(qs)
    discard_array(qs)
    output("c", bits)


def test_guppy_program_with_classical_control_lowers_to_valid_qir():
    qir = guppy_to_qir_str(teleport_one)
    qircheck(qir)
    assert "__quantum__qis__mz__body" in qir
    assert "__quantum__rt__initialize" in qir
    # Mid-circuit measurements feed back into conditional corrections.
    assert "br i1" in qir


@pytest.mark.parametrize("output_format", [OutputFormat.LLVM_IR, OutputFormat.BITCODE])
def test_serialized_pytket_derived_hugr_lowers_to_valid_qir(output_format):
    hugr_bytes = run_ghz_circuit.compile().to_bytes()
    qir = hugr_to_qir(Package.from_bytes(hugr_bytes), output_format=output_format)
    assert isinstance(qir, bytes if output_format == OutputFormat.BITCODE else str)
    qircheck(qir)
