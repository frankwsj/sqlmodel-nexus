# Implementation Plan: Compose Schema — INPUT_OBJECT Handling for Method Args

**Branch**: `003-compose-input-object` | **Date**: 2026-06-24 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-compose-input-object/spec.md`

## Summary

Port the three INPUT_OBJECT introspection correctness fixes from pydantic-resolve v5.10.2 (commit `184886d`) into nexusx's own `nexusx.use_case.compose_schema` + `compose_type_mapper`. Today nexusx registers every Pydantic `BaseModel` as a GraphQL `OBJECT` regardless of return-vs-arg position, which (a) violates the GraphQL spec for any method that takes a BaseModel arg, (b) crashes with `DuplicateTypeError` when the same class is used as both return and arg, and (c) emits method SDL that references undefined input types. The fix activates nexusx's existing-but-dormant `INPUT_OBJECT` leaf kind via an `is_input` codepath through the mapper, a two-phase build that renames arg-side registrations to `{Name}Input` on conflict, and a closure walk that recurses through INPUT_OBJECT `input_fields`. See [research.md](research.md) for the 8 design decisions, [data-model.md](data-model.md) for the metadata-struct deltas, and [contracts/](contracts/) for the observable shapes.

## Technical Context

**Language/Version**: Python 3.10+ (project floor at `pyproject.toml`: `requires-python = ">=3.10"`).

**Primary Dependencies**:
- `pydantic>=2.0` — `BaseModel`, `model_fields`, the `PydanticUndefined` sentinel (new import in this feature).
- `graphql-core>=3.2.0` — `graphql.build_client_schema` used in tests as the spec-compliance gate (FR-008 / SC-002).
- No new third-party deps. See [research.md](research.md) Decision 7.

**Storage**: N/A — metadata builder only; no DB touch. (Phase 0 Step 0-7 in `spec.md` is N/A for this feature.)

**Testing**: pytest. New file `tests/test_compose_introspection.py` mirrors upstream's `tests/use_case/test_compose_introspection.py` (307 lines, 7 test classes — see [research.md](research.md) Decision 8). Existing `tests/test_compose_schema.py` / `test_compose_introspect.py` / `test_compose_executor.py` / `test_compose_mcp_server.py` serve as the regression suite (FR-009).

**Target Platform**: Linux/macOS dev hosts running CPython 3.10–3.12. The feature is pure-Python with no platform-specific code.

**Project Type**: Library (nexusx is published as a library; the compose surface is one of its modules).

**Performance Goals**: Schema build time must not regress measurably for the common case (no BaseModel args). Two-phase build adds one extra pass over the method list, but per-method work is unchanged. No performance SLO exists for this surface today.

**Constraints**:
- `TypeInfo` / `FieldInfo` / `ArgumentInfo` remain `@dataclass(frozen=True, slots=True)` — fix must work without mutation.
- The public signatures of `build_compose_schema`, `ComposeSchema`, `compose_introspect`, and `render_method_sdl` are unchanged — only their output content evolves.
- No `python_type: Any` field on FieldInfo (upstream-style) — nexusx's `type_ref`-baked approach is preserved ([research.md](research.md) "Architectural delta").

**Scale/Scope**: ~150–250 lines of code change across `src/nexusx/use_case/compose_schema.py` (827 lines today) and `src/nexusx/use_case/compose_type_mapper.py`; ~300 lines of new tests. Single-PR scope.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The project constitution at `.specify/memory/constitution.md` is in placeholder form (`[PRINCIPLE_1_NAME]`, `[PRINCIPLE_1_DESCRIPTION]`, …) — no ratified principles to check against. The gate is therefore trivially satisfied. Re-evaluation after Phase 1 design: still no ratified principles; no violations to justify.

**Recommendation** (out of scope for this feature, surfaced for the user): run `/speckit-constitution` separately to ratify the placeholder principles. The compose-surface code does have implicit conventions worth codifying — frozen dataclasses, type-ref-baked-at-build-time, two-pass builds for name uniqueness — but those belong in a constitution PR, not in this bug-fix port.

## Project Structure

### Documentation (this feature)

```text
specs/003-compose-input-object/
├── plan.md                # This file
├── spec.md                # /speckit-specify output
├── research.md            # Phase 0 — 8 design decisions
├── data-model.md          # Phase 1 — metadata-struct deltas
├── quickstart.md          # Phase 1 — runnable validation guide
├── contracts/
│   ├── registry-shape.md        # build_compose_schema output contract
│   ├── introspection-json.md    # compose_introspect INPUT_OBJECT rendering
│   └── method-sdl.md            # render_method_sdl INPUT_OBJECT blocks
└── tasks.md               # Phase 2 — NOT created by /speckit-plan (run /speckit-tasks)
```

### Source Code (repository root)

```text
src/nexusx/use_case/
├── compose_schema.py          #TypeInfo/FieldInfo/ArgumentInfo dataclasses,
│                              # build_compose_schema (two-phase restructure),
│                              # _collect_closure (INPUT_OBJECT recursion + arg seeding),
│                              # _emit_type_sdl (input_fields source), render_method_sdl
├── compose_type_mapper.py     # map_python_type_as_input(), _map_leaf(is_input=...),
│                              # _register_input_object() with rename-on-conflict
├── compose_introspect.py      # unchanged — already delegates to render_introspection
├── compose_executor.py        # unchanged — input-object handling at exec time was already correct
└── compose_mcp_server.py      # unchanged — pure consumer of the schema

tests/
├── test_compose_introspection.py    # NEW — 7 test classes ported from upstream
├── test_compose_schema.py           # existing — regression
├── test_compose_introspect.py       # existing — regression
├── test_compose_executor.py         # existing — regression
└── test_compose_mcp_server.py       # existing — regression
```

**Structure Decision**: Single-project library layout (Option 1 in the template). All changes are scoped to `src/nexusx/use_case/` (the compose surface) and `tests/`. No new packages, no new top-level modules.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

N/A — Constitution Check has no ratified principles to violate.

---

## Phase 1: Schema + ER + Mock Seed (nexusx)

> **Applicability note**: This section of the nexusx-4phase preset assumes Phase 1 = "build the consumer app's SQLModel entities + ER diagram + mock seed". For THIS feature — a bug-fix port into nexusx's own metadata builder — Phase 1 in that sense does not exist. There are no business entities, no DB, no Voyager ER. The preset's Phase 1 deliverables map onto **metadata-model design** instead, captured in [data-model.md](data-model.md) and [contracts/](contracts/). The subsections below record the mapping and mark the preset's business-app assumptions as N/A where they don't apply.

### Files to Create / Modify

| File | Action | Purpose |
|------|--------|---------|
| `src/nexusx/use_case/compose_type_mapper.py` | modify | Add `is_input` plumbing, `map_python_type_as_input`, `_register_input_object` with rename-on-conflict |
| `src/nexusx/use_case/compose_schema.py` | modify | `TypeInfo.python_class` + `FieldInfo.default_value`; restructure `build_compose_schema` into two phases; extend `_collect_closure` to recurse INPUT_OBJECT + seed from args; extend `_emit_type_sdl` to read `input_fields` for INPUT_OBJECT |
| `tests/test_compose_introspection.py` | create | 7 test classes ported from upstream `tests/use_case/test_compose_introspection.py` |
| `src/db.py` / `src/models.py` / `src/database.py` / `src/main.py` | **N/A** | These preset-prescribed files are for consumer apps, not for nexusx itself. nexusx has no DB. |
| `alembic/` | **N/A** | Same — no DB schema to migrate. |

### Models Conventions

**N/A — see note.** The preset's SQLModel conventions (`Field(description=...)`, `sa_relationship_kwargs={"lazy": "noload"}`, directory-name rules) apply to consumer apps built on nexusx. This feature modifies nexusx's internal pydantic-based metadata structs, which already follow their own conventions (`@dataclass(frozen=True, slots=True)`, type-ref-baked-at-build-time — see [research.md](research.md) "Architectural delta").

### DB Persistence Branch

**N/A — see note.** Phase 0 Step 0-7 was confirmed N/A in [spec.md](spec.md). No `db.py`, no `DATABASE_URL`, no alembic, no docker-compose.

### Voyager Visualization

**N/A — see note.** Voyager visualizes business-app ER diagrams. This feature has no entities to visualize. The closest analog — a structural diagram of the metadata structs (`TypeRef`/`TypeInfo`/`FieldInfo`/`ArgumentInfo`) — is captured textually in [data-model.md](data-model.md#activation-matrix-what-changes-per-leaf-kind) as the "activation matrix".

### Phase 1 Pitfalls

The preset's 6 pitfalls (circular imports, `packages = ["src"]`, in-memory SQLite process locality, `uvicorn --reload` interaction with `db.py`, alembic autogenerate empty migrations, `NameError: sqlmodel`) all assume a consumer app with a DB. **None apply** to this feature.

The feature has its OWN pitfalls, surfaced as risks in [research.md](research.md):

1. **Phase ordering** — phase A (returns) MUST complete before phase B (args). Interleaving per-method produces an inconsistent registry.
2. **Rename-on-conflict only triggers on identity match** — two distinct classes sharing a `__name__` still raise `DuplicateTypeError` (preserved guard, not weakened).
3. **`type_ref` is frozen at build time** — there's no render-time name-override escape hatch like upstream's `_override_input_name`. The build-time rename in `_register_input_object` is the only chance to get the leaf name right.
4. **`input_fields` vs `fields` source** — `_emit_type_sdl` must read `t.input_fields` for `kind == INPUT_OBJECT`, not `t.fields`. Today's code reads `t.fields` unconditionally.
5. **`_collect_closure` recursion** — today the comment says "SCALAR / ENUM / INPUT_OBJECT: leaf, no further recursion needed". After the fix, INPUT_OBJECT must recurse through `input_fields`.
6. **Mutable pydantic defaults** (`default_factory=list`) — not representable as a GraphQL literal. Treat as "no default" (matches upstream).

### Phase 1 V-Model Acceptance Criteria

For a bug-fix port, the V-model maps onto testable behaviors, not onto "Voyager shows the ER diagram". Recorded as the 5 quickstart scenarios in [quickstart.md](quickstart.md) and the 9 FRs in [spec.md](spec.md#functional-requirements):

| # | Criterion | Verification |
|---|-----------|--------------|
| 1 | BaseModel arg registers as INPUT_OBJECT with populated inputFields | [quickstart.md](quickstart.md) Scenario 1 |
| 2 | Same model as return+arg does not crash and produces `{Name}Input` rename | [quickstart.md](quickstart.md) Scenario 2 |
| 3 | Method SDL expands INPUT_OBJECT closure including nested inputs | [quickstart.md](quickstart.md) Scenario 3 |
| 4 | GraphiQL round-trip via `graphql.build_client_schema` succeeds | [quickstart.md](quickstart.md) Scenario 4 |
| 5 | No regressions in existing compose test suite (byte-identical output for no-arg apps) | [quickstart.md](quickstart.md) Scenario 5 |

These five are the Phase 1 acceptance gate. Implementation (`/speckit-tasks`) must not start until the user confirms this mapping is acceptable.

### Hand-off

`/speckit-tasks` next, to break the implementation work in `compose_schema.py` + `compose_type_mapper.py` + the new test file into ordered, dependency-tracked tasks. Suggested task shape:
1. Metadata struct additions (`TypeInfo.python_class`, `FieldInfo.default_value`) — unblocks everything.
2. `compose_type_mapper` is_input plumbing + `_register_input_object`.
3. `build_compose_schema` two-phase restructure.
4. `_collect_closure` + `_emit_type_sdl` extensions.
5. New `tests/test_compose_introspection.py`.
6. Regression sweep + manual sanity probe.

(Concrete task breakdown belongs in `tasks.md`, produced by `/speckit-tasks`.)
