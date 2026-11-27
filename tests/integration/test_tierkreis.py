"""Tierkreis workflows and their typed interfaces to the other SDK components."""

import asyncio
import importlib
import re
from pathlib import Path
from typing import NamedTuple

import pytest
from guppy_worker import from_circuit, normalize
from nexus_worker import upload_hugr
from pytket_worker import from_qasm2_str
from tierkreis.builder import Graph
from tierkreis.builtins import iadd, itimes
from tierkreis.models import TKR, OpaqueType
from tierkreis.runtime import new_in_memory

# Worker interfaces, from the tkr-*-worker packages, that exchange SDK objects
# (circuits, HUGR packages, backend configs, results) between workflow nodes.
SDK_WORKERS = [
    "guppy_worker",
    "nexus_worker",
    "pytket_worker",
    "quantinuum_worker",
]


class Inputs(NamedTuple):
    value: TKR[int]


def build_workflow():
    graph = Graph(Inputs, TKR[int])
    product = graph.task(itimes(graph.inputs.value, graph.const(5)))
    return graph.finish_with_outputs(graph.task(iadd(product, graph.const(1))))


class UploadInputs(NamedTuple):
    qasm: TKR[str]
    project_name: TKR[str]


def build_upload_workflow():
    """Chain the pytket, guppy, and nexus workers: QASM to a Nexus HUGR upload."""
    graph = Graph(UploadInputs, TKR[OpaqueType["qnexus.models.references.HUGRRef"]])
    circuit = graph.task(from_qasm2_str(graph.inputs.qasm))
    package = graph.task(from_circuit(circuit, graph.const("main")))
    package = graph.task(normalize(package))
    return graph.finish_with_outputs(
        graph.task(upload_hugr(package, graph.inputs.project_name))
    )


async def run_workflow(value):
    runtime = await new_in_memory()
    with runtime:
        workflow_id = await runtime.save_workflow(
            "times five plus one", build_workflow()
        )
        run_id = await runtime.start_new_run(workflow_id, {"value": value})
        await runtime.wait_for(run_id, 0, timeout=60)
        return await runtime.get_outputs(run_id)


def test_builtin_workflow_runs_in_memory():
    assert asyncio.run(run_workflow(3)) == 16


async def save_workflow(name, workflow):
    runtime = await new_in_memory()
    with runtime:
        return await runtime.save_workflow(name, workflow)


def test_workflow_across_sdk_workers_builds_and_saves():
    # Running it needs the separately deployed workers and Nexus access.
    assert asyncio.run(save_workflow("qasm to nexus", build_upload_workflow()))


def opaque_types(worker):
    source = Path(importlib.import_module(worker).__file__).read_text(encoding="utf-8")
    return sorted(set(re.findall(r'OpaqueType\["([\w.]+)"\]', source)))


@pytest.mark.parametrize("worker", SDK_WORKERS)
def test_worker_interfaces_reference_installed_sdk_types(worker):
    names = opaque_types(worker)
    assert names
    for name in names:
        module, _, attribute = name.rpartition(".")
        assert isinstance(getattr(importlib.import_module(module), attribute), type), (
            name
        )
