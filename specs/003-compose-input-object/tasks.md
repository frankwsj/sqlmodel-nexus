---

description: "Task list for porting pydantic-resolve v5.10.2 INPUT_OBJECT fixes into nexusx compose_schema"
---

# Tasks: Compose Schema — INPUT_OBJECT Handling for Method Args

**Input**: Design documents from `/specs/003-compose-input-object/`

**Prerequisites**: [plan.md](plan.md) (required), [spec.md](spec.md) (required), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: INCLUDED — the upstream reference commit added 307 lines of tests, and FR-008 / SC-002 make `graphql.build_client_schema` round-trip a load-bearing acceptance gate. Tests cannot be optional here.

**Organization**: Tasks grouped by user story (US1 → US2 → US3) per the core workflow. The nexusx-4phase preset's Phase 1/2/3/4 mapping (SQLModel entities → methods.py → service.py/main.py → TS SDK) assumes a **consumer app built on nexusx**; it does not apply to a bug-fix port of nexusx's own internals and is intentionally not used below. The `[USx]` labels track which spec user story each task delivers.

## Format: `[ID] [P?] [Story?] Description (file path)`

- **[P]**: parallel-safe — different file or non-overlapping region, no dep on incomplete tasks
- **[USx]**: maps to spec.md user story x
- Every task names the exact file path it touches

---

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: Metadata-struct additions + `is_input` plumbing through the type mapper. MUST complete before any user story work — every subsequent task depends on these fields/params existing.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T001 Add `python_class: type | None = None` field to `TypeInfo` dataclass in `src/nexusx/use_case/compose_schema.py:128-138`. Default `None` keeps SCALAR/ENUM registrations unchanged. Field is internal bookkeeping — never serialized.
- [X] T002 ~~Add `default_value: Any = None` field to `FieldInfo`~~ **REVERTED during US1 implementation** — nexusx's `TypeInfo.input_fields: tuple[ArgumentInfo, ...]` (not FieldInfo), and `ArgumentInfo` already has `default_value`. The FieldInfo addition was dead code based on a misread of upstream (which uses FieldInfo for both OBJECT fields and input_fields polymorphically). Kept the Foundational change minimal per CLAUDE.md.
- [X] T003 Add `map_python_type_as_input(py_type: Any) -> TypeRef` public method to `ComposeTypeMapper` in `src/nexusx/use_case/compose_type_mapper.py`. Body calls `self._map(py_type, force_nullable=False, is_input=True)`. Default `is_input=False` path stays on existing `map_python_type`.
- [X] T004 Thread `is_input: bool = False` param through `_map` → `_map_list` → `_map_optional` → `_map_leaf` in `src/nexusx/use_case/compose_type_mapper.py`. Containers propagate `is_input` unchanged; only `_map_leaf` reads it (Decision 1 in [research.md](research.md)).

**Checkpoint**: Metadata structs have the new fields; mapper accepts `is_input` end-to-end but no behavior changes yet (BaseModel still routes to `_register_object` regardless). Existing tests still green.

---

## Phase 2: User Story 1 — BaseModel arg registers as INPUT_OBJECT (Priority: P1) 🎯 MVP

**Goal**: A method `create_task(payload: CreateTaskInput)` produces a registry entry of `kind=INPUT_OBJECT` with populated `input_fields` and pydantic-default literals — validated end-to-end against [contracts/registry-shape.md](contracts/registry-shape.md).

**Independent Test**: [quickstart.md](quickstart.md) Scenario 1 — `uv run pytest tests/test_compose_introspection.py::TestInputTypeEdgeCases -k payload_arg_registers -v`.

### Tests for User Story 1 (write first, must FAIL before implementation)

- [X] T005 [P] [US1] Create `tests/test_compose_introspection.py` with `TestInputTypeEdgeCases` class and port `test_input_payload_arg_registers_input_object_type` from upstream `tests/use_case/test_compose_introspection.py`. Include any required demo app fixture (TaskService + CreateTaskInput BaseModel).
- [X] T006 [P] [US1] Port `test_input_field_default_value_preserved` (asserts `priority.default_value == 5`, `note.default_value is None`) into `tests/test_compose_introspection.py::TestInputTypeEdgeCases`.
- [X] T007 [P] [US1] Port `test_optional_input_field_is_nullable` + `test_list_input_field_nullability` into `tests/test_compose_introspection.py::TestInputTypeEdgeCases`.

### Implementation for User Story 1

- [X] T008 [US1] Implement `_register_input_object(cls)` method on `ComposeTypeMapper` in `src/nexusx/use_case/compose_type_mapper.py`. Builds `TypeInfo(kind="INPUT_OBJECT", python_class=cls, input_fields=(...))`; each input field's `default_value` set via new `_field_default_literal(field_info)` helper (returns `None` for `PydanticUndefined`, otherwise the raw Python default — see Decision 7 in [research.md](research.md)). Add `from pydantic_core import PydanticUndefined` import. **No rename-on-conflict logic yet** (that's T013 in US2).
- [X] T009 [US1] Branch `_map_leaf` in `src/nexusx/use_case/compose_type_mapper.py:254-256`: when `is_input=True` and `issubclass(py_type, BaseModel)`, call `_register_input_object`; otherwise existing `_register_object`. Scalars/enums ignore `is_input`.
- [X] T010 [US1] Restructure `build_compose_schema` in `src/nexusx/use_case/compose_schema.py:241-351` into two phases per Decision 4: (A.1) collect `method_metas` once, register all return OBJECTs; (A.2) walk args, register all INPUT_OBJECTs via `map_python_type_as_input`; (A.3) assemble `FieldInfo` + `ArgumentInfo`. Phase ordering load-bearing — returns before args.
- [X] T011 [US1] Update `_build_method_arguments` in `src/nexusx/use_case/compose_schema.py:429-482` to call `mapper.map_python_type_as_input(annotation)` instead of `mapper.map_python_type(annotation)`.
- [X] T012 [US1] Update `_render_introspection` / `_type_info_to_introspection` in `src/nexusx/use_case/compose_schema.py:617-668` to populate `inputFields` from `t.input_fields` when `kind == INPUT_OBJECT` (currently hardcoded to None at line 639 + 651). See [contracts/introspection-json.md](contracts/introspection-json.md).

**Checkpoint**: User Story 1 green. `build_compose_schema` for an app with BaseModel args produces a spec-correct registry. **Commit here** — this is the MVP.

---

## Phase 3: User Story 2 — Same model as return AND arg does not crash (Priority: P2)

**Goal**: `upsert_task(patch: TaskDTO) -> TaskDTO` produces both `TaskDTO` (OBJECT) and `TaskDTOInput` (INPUT_OBJECT); no `DuplicateTypeError`; nested input closure stays consistent. See [contracts/registry-shape.md](contracts/registry-shape.md#behavioral-rules-load-bearing-for-consumers).

**Independent Test**: [quickstart.md](quickstart.md) Scenario 2 — `uv run pytest tests/test_compose_introspection.py::TestInputTypeEdgeCases -k both_return_and_arg -v`.

### Tests for User Story 2 (write first, must FAIL before implementation)

- [X] T013 [P] [US2] Port `test_dto_used_as_both_return_and_arg_arg_is_input_object` into `tests/test_compose_introspection.py::TestInputTypeEdgeCases`. Asserts: no exception, both `TaskDTO` + `TaskDTOInput` in registry, `args[0].type_ref` leaf name is `TaskDTOInput`.
- [X] T014 [P] [US2] Port `test_nested_basemodel_in_input_registers_as_input_object` into `tests/test_compose_introspection.py::TestInputTypeEdgeCases`. Asserts nested-input closure consistency: `OuterInput.inner` → `InnerInputInput` (renamed leaf used everywhere).

### Implementation for User Story 2

- [X] T015 [US2] Extend `_register_input_object` in `src/nexusx/use_case/compose_type_mapper.py` (built in T008) with rename-on-conflict branch per Decision 3: when candidate name is already in `_registry` AND the existing entry's `python_class is cls` AND its `kind == OBJECT` → rename candidate to `f"{cls.__name__}Input"`. When existing entry's `python_class is not cls` → still raise `DuplicateTypeError` (distinct-class guard preserved).
- [X] T016 [US2] Verify in `src/nexusx/use_case/compose_type_mapper.py` that `_by_python_id[id(cls)]` is updated to point at the renamed INPUT_OBJECT TypeInfo (not the original OBJECT) when the input version wins the id slot. This is what makes subsequent references from sibling input fields resolve to the renamed leaf automatically.

**Checkpoint**: User Story 2 green. Existing `tests/test_compose_schema.py::TestDedup::test_two_distinct_classes_with_same_name_raises` still passes (the distinct-class guard must not regress).

---

## Phase 4: User Story 3 — Method SDL expands INPUT_OBJECT types (Priority: P3)

**Goal**: `render_method_sdl("TaskService", "create_task")` includes `input CreateTaskInput { ... }` and all nested input blocks. See [contracts/method-sdl.md](contracts/method-sdl.md).

**Independent Test**: [quickstart.md](quickstart.md) Scenario 3 — `uv run pytest tests/test_compose_introspection.py::TestInputTypeEdgeCases -k method_sdl_expands -v`.

### Tests for User Story 3 (write first, must FAIL before implementation)

- [X] T017 [P] [US3] Port `test_method_sdl_expands_input_object_referenced_by_args` into `tests/test_compose_introspection.py::TestInputTypeEdgeCases`. Asserts the SDL string contains both `input CreateTaskInput { ... }` and any nested `input NestedInput { ... }`, with no referenced-but-undefined type.

### Implementation for User Story 3 (all three sub-tasks touch non-overlapping regions of compose_schema.py — parallel-safe)

- [X] T018 [P] [US3] Extend `_collect_closure` in `src/nexusx/use_case/compose_schema.py:776-801` to recurse through INPUT_OBJECT `input_fields[*].type_ref` (today's comment says "leaf, no recursion" — needs branch for `kind == INPUT_OBJECT`).
- [X] T019 [P] [US3] Update `_render_method_sdl` in `src/nexusx/use_case/compose_schema.py:711-775` to seed the closure walk from EACH arg's `type_ref` in addition to `method_field.type_ref`. Today only seeds from return type.
- [X] T020 [P] [US3] Branch `_emit_type_sdl` in `src/nexusx/use_case/compose_schema.py:803-827` to read `t.input_fields` (a `tuple[ArgumentInfo, ...]`) when `t.kind == INPUT_OBJECT`, instead of `t.fields`. Existing `keyword = "type" if t.kind == OBJECT else "input"` at line 819 already produces the right keyword — only the field source needs branching.

**Checkpoint**: User Story 3 green. All three user stories now independently functional.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Spec-compliance gate + regression sweep + sanity probe. Affects all user stories.

- [X] T021 [P] Port `TestGraphiQLCompatibility::test_canonical_graphiql_introspection_query_works` into `tests/test_compose_introspection.py`. Runs the canonical GraphiQL introspection query through `compose_introspect`, then feeds the result to `graphql.build_client_schema(introspection_json)` — MUST NOT raise. This is the FR-008 / SC-002 gate.
- [X] T022 Run full regression sweep: `uv run pytest tests/test_compose_schema.py tests/test_compose_introspect.py tests/test_compose_executor.py tests/test_compose_mcp_server.py tests/test_compose_old_api_removed.py tests/test_compose_introspection.py -q`. All must pass (FR-009 / SC-003).
- [X] T023 Byte-equivalence check for no-arg apps (FR-009 / SC-003): build a `ComposeSchema` from a service in `tests/test_compose_schema.py` that declares zero BaseModel method args, dump `registry` to JSON, compare against the same dump from the `master` branch. Must be byte-identical (same type names, kinds, fields, args).
- [X] T024 Run the manual sanity probe from [quickstart.md](quickstart.md) ("Manual sanity probe" section) against the demo service in `tests/test_compose_introspection.py` and eyeball the SDL + introspection JSON output against [contracts/method-sdl.md](contracts/method-sdl.md) + [contracts/introspection-json.md](contracts/introspection-json.md).
- [X] T025 [P] If nexusx tracks its own version + changelog (check `pyproject.toml` + any `CHANGELOG.md`), bump patch version and add a `5.10.2-equivalent` entry describing the three ported fixes. Skip if nexusx versioning is independent of upstream.

**Final Checkpoint**: All Phase 2–5 tests green; regression suite unchanged; manual probe confirms spec-compliant output.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Foundational)**: No deps. Blocks all user story work.
- **Phase 2 (US1)**: Depends on Phase 1. MVP — delivers the core INPUT_OBJECT registration.
- **Phase 3 (US2)**: Depends on Phase 2 (US2's rename branch extends `_register_input_object` built in T008).
- **Phase 4 (US3)**: Depends on Phase 1 only. The closure/SDL work is independent of the registration work in US1/US2 — could run in parallel with US2 if staffed.
- **Phase 5 (Polish)**: Depends on US1 + US2 + US3 (the GraphiQL gate exercises all three).

### Within Each User Story

- Tests written FIRST (TDD) — must fail before implementation
- Mapper / registration before schema-builder restructure
- Schema builder before renderer (introspection/SDL)
- Run acceptance scenario from [quickstart.md](quickstart.md) before moving on

### Parallel Opportunities

- T001/T002 (different dataclasses, same file) — borderline parallel; safer sequential.
- T005/T006/T007 (different test methods, same new file) — parallel-safe once file is created by T005.
- T013/T014 (different test methods) — parallel-safe.
- T017 (single test) — alone.
- T018/T019/T020 (different functions in compose_schema.py) — parallel-safe per Decision 5/6 in [research.md](research.md).
- T021/T025 (different files) — parallel-safe.

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1 (Foundational) → structs + mapper plumbing ready.
2. Complete Phase 2 (US1) → core INPUT_OBJECT registration works.
3. **STOP and VALIDATE**: run `pytest tests/test_compose_introspection.py::TestInputTypeEdgeCases -k payload_arg_registers`.
4. At this point the primary spec violation (args rendered as OBJECT) is fixed for the common case. Ship if only that matters.

### Incremental Delivery

5. Add Phase 3 (US2) → unblocks apps that reuse DTOs as both input and output.
6. Add Phase 4 (US3) → AI-agent / docs SDL becomes self-contained.
7. Add Phase 5 (Polish) → GraphiQL round-trip gate green; regressions clean.

### Suggested commit boundaries

- After T004: "compose_schema: add python_class/default_value fields + is_input mapper plumbing (no behavior change)"
- After T012: "compose_schema: register BaseModel args as INPUT_OBJECT (User Story 1)"
- After T016: "compose_schema: rename arg-side types to {Name}Input on conflict (User Story 2)"
- After T020: "compose_schema: expand INPUT_OBJECT closure in method SDL (User Story 3)"
- After T024: "compose_schema: GraphiQL round-trip gate + regression sweep (Polish)"

---

## Notes

- `[P]` tasks = different files or non-overlapping regions, no deps on incomplete tasks.
- `[USx]` label maps task to spec user story x for traceability.
- Every implementation task references [research.md](research.md) decisions and [contracts/](contracts/) for the exact expected shape.
- The upstream reference commit is `184886d` at `/home/tangkikodo/pydantic-resolve/` — `tests/use_case/test_compose_introspection.py` (307 lines) is the source of truth for test intent. Port intent, not line-for-line code (nexusx's dataclass shape differs per [research.md](research.md) "Architectural delta").
- nexusx's existing `tests/test_compose_schema.py::TestDedup::test_two_distinct_classes_with_same_name_raises` already covers the distinct-class guard — T015 must not regress it.
- Avoid: touching `compose_executor.py` (input-object handling at exec time was already correct — only the schema was wrong).
