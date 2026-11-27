# SDK integration test report

Date: 2026-11-27

Findings from writing `tests/integration/` against the pinned SDK components
in `pyproject.toml` (quantinuum-nexus 26.1.0). Each failure below is a documented
example or a combination of components that should work but does not with the
pinned versions.

## README failures (not tested)

README examples that failed with the pinned versions. They are tracked by the
upstream issues or fixes below rather than by tests, because a test that kept a
copy of an old README would not follow later changes to it. The tests run the
remaining README examples from the installed packages' metadata.

### 1. selene-sim README: measurements passed to `result()`

- Components: selene-sim 0.3.8 README, guppylang 1.2.3
- Status: open upstream issue
  [Quantinuum/selene#282](https://github.com/Quantinuum/selene/issues/282); the
  README on selene `main` still has this example.
- The README's GHZ program reports `result("measurements", measure_array(qubits))`.
  Since guppylang 1.x, `measure_array` returns lazy `Measurement` values, which
  `result`/`output` do not accept:

  ```text
  Error: Unsupported output value type
  Help: Use `collect_measurements()` on the array to get an array of bools
  ```

- Fix: `result("measurements", collect_measurements(measure_array(qubits)))`.
  `result` is a deprecated alias of `output` that Guppy makes available in every
  `@guppy` function; it is not exported by `guppylang.std.quantum`. Using
  `output` imported from `guppylang.std.builtins` would avoid the deprecation.
  The selene-sim README tests apply this fix before running the later examples.

### 2. selene-sim README: `runner.run(..., n_shots=...)`

- Components: selene-sim 0.3.8
- Status: fixed on selene `main`, which no longer has this example; awaiting a
  selene-sim release after 0.3.8. Mentioned in
  [Quantinuum/selene#282](https://github.com/Quantinuum/selene/issues/282).
- The README's multi-shot example calls `runner.run(simulator=..., n_qubits=10,
  n_shots=100, n_processes=8)` and wraps it in `QsysShot`, while its comment says
  `run_shots` should be used:

  ```text
  TypeError: SeleneInstance.run() got an unexpected keyword argument 'n_shots'
  ```

- Fix: `QsysResult(runner.run_shots(...))`, as the README's later error-model
  examples already do (those pass).

### 3. guppyft README: `SteaneBuilder().build(n_blocks=3)`

- Components: guppyft 0.7.0
- Status: fixed on guppyft `main` by
  [Quantinuum/guppyft#578](https://github.com/Quantinuum/guppyft/pull/578);
  awaiting a guppyft release after 0.7.0, so no issue was opened.
- `SteaneBuilder.build()` takes no arguments:

  ```text
  TypeError: SteaneBuilder.build() got an unexpected keyword argument 'n_blocks'
  ```

- Fix: `SteaneBuilder.new(n_blocks=3).build()` (or
  `SteaneBuilder().with_n_blocks(3).build()`). With that change the README
  program encodes and emulates correctly; `test_guppyft.py` covers it.

## Component failures (xfail)

Combinations of components that should work but fail. The tests are marked
`xfail(strict=True)`, so they start failing (XPASS) once the issue is fixed and
the marker should be removed.

### 4. hugr-qir cannot lower guppyft-encoded programs

- Components: guppyft 0.7.0, hugr-qir 0.4.0
- Test: `test_guppyft.py::test_steane_encoded_program_lowers_to_qir`
- Status: open upstream issue
  [Quantinuum/hugr-qir#451](https://github.com/Quantinuum/hugr-qir/issues/451).
- A Steane-encoded teleportation program emulates correctly on Selene, but
  `hugr_to_qir` on the same encoded package fails, and asks for a bug report:

  ```text
  ValueError: Compilation failed unexpectedly: Failed to emit LLVM for function
  guppyft.encode._implement_ops.implement_ops.<locals>.outer_wrapper at node
  Node(1) This may be a compiler bug. Please report it with a reproducing example.
  ```

- An unencoded teleportation program lowers to valid QIR (`test_hugr_qir.py`), so the
  failure is in lowering guppyft's generated wrapper functions.

## Observations (not failures)

- Every Selene emulation emits `DeprecationWarning: Use
  EmulatorState.from_bytes(...).compile_to_bitcode(...) instead` from
  `selene_helios_qis_plugin/build.py` (selene-sim 0.3.8), which calls an API
  that selene-hugr-qis-compiler 0.5.3 deprecates.
- `tket.passes.NormalizeGuppy` is deprecated in favour of `Normalize`.
- `quantinuum_schemas` warns that `SeleneConfig(n_qubits=...)` is ignored; the
  qubit count is no longer part of the Nexus Selene configuration.
- tierkreis 3.1.0 ships typed stubs for its `guppy_worker`, `pytket_worker`,
  `nexus_worker`, and `quantinuum_worker`, but not the workers themselves. A
  workflow using them can be built and saved, but fails at runtime unless the
  workers are deployed separately. The stubs are removed from tierkreis after
  3.1.0 ([Quantinuum/tierkreis#843](https://github.com/Quantinuum/tierkreis/pull/843))
  in favour of the identical `tkr-guppy-worker`, `tkr-nexus-worker`,
  `tkr-pytket-worker`, and `tkr-quantinuum-worker` packages, which are not part of
  the metapackage. The tests install these from the `integration` dependency
  group, check that their SDK types exist in the pinned packages, and run a
  built-in workflow end to end.
- guppyalgos' Cuccaro adder uses non-Clifford Toffoli decompositions, so it
  needs Selene's statevector simulator; Stim rejects its `RZ(pi/4)` gates. This
  is expected behaviour.
- guppyalgos' state preparation lowers to valid QIR, but its Cuccaro adder and
  QFT do not, for documented limitations of the H-series QIR target rather than
  bugs: the adder may panic (`Option.unwrap`, and runtime panics are unsupported
  on H2), and the QFT has loops that cannot be unrolled at compile time (even
  with `max_loop_unroll=100000`). They run on Selene, which is tested.
- `tierkreis.data.types.is_ptype(EmulatorResult)` is false, although the
  `guppy_worker.emulate` stub returns one. This is not a failure: the deployed
  worker (`tierkreis_workers/guppy_worker` in the tierkreis repository) wraps
  the result with a custom tierkreis `Serializer`.
