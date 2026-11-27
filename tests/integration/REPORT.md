# SDK integration test report

Findings from writing `tests/integration/` against the pinned SDK components
in `pyproject.toml` (quantinuum-nexus 26.1.0). Each failure below is a documented
example or a combination of components that should work but does not with the
pinned versions. The corresponding tests are marked `xfail(strict=True)`, so they
start failing (XPASS) once the issue is fixed and the marker should be removed.
README examples are read from the installed packages' metadata, so a fix in a
newly pinned README is picked up without editing the tests.

## Failures (xfail)

### 1. selene-sim README: measurements passed to `result()`

- Components: selene-sim 0.3.8 README, guppylang 1.2.3
- Test: `test_selene_readme_program`
- Upstream: Quantinuum/selene#282
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

### 2. selene-sim README: `runner.run(..., n_shots=...)`

- Components: selene-sim 0.3.8
- Test: `test_selene_readme_multi_shot`
- Upstream: already removed from the README on selene `main`; fixed in the next
  release (see Quantinuum/selene#282)
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
- Test: `test_guppyft_readme`
- Upstream: fixed on guppyft `main` by Quantinuum/guppyft#578; fixed in the next
  release
- `SteaneBuilder.build()` takes no arguments:

  ```text
  TypeError: SteaneBuilder.build() got an unexpected keyword argument 'n_blocks'
  ```

- Fix: `SteaneBuilder.new(n_blocks=3).build()` (or
  `SteaneBuilder().with_n_blocks(3).build()`). With that change the README
  program encodes and emulates correctly; `test_guppyft.py` covers it.

### 4. hugr-qir cannot lower guppyft-encoded programs

- Components: guppyft 0.7.0, hugr-qir 0.4.0
- Test: `test_guppyft.py::test_steane_encoded_program_lowers_to_qir`
- Upstream: Quantinuum/hugr-qir#451
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
- Tierkreis ships typed stubs for its `guppy_worker`, `pytket_worker`,
  `nexus_worker`, and `quantinuum_worker`, but not the workers themselves. A
  workflow using them can be built and saved, but fails at runtime unless the
  workers are deployed separately. The tests check the stubs' SDK types exist in
  the pinned packages and run a built-in workflow end to end.
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
