# Quickstart: Validate the INPUT_OBJECT Fixes

**Feature**: 003-compose-input-object
**Purpose**: End-to-end validation that the three introspection fixes from pydantic-resolve v5.10.2 are faithfully ported. Reference: [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/).

This guide runs the existing + new test suite and shows what "green" looks like for each of the three user stories. **No implementation code lives here** — that's `tasks.md`'s job.

---

## Prerequisites

```bash
# Project venv with pyyaml + graphql-core (dev deps)
uv sync --all-extras

# Sanity: existing compose tests pass (the regression baseline)
uv run pytest tests/test_compose_schema.py tests/test_compose_introspect.py -q
```

If any of the above fail, stop — the feature must not be developed on top of a red baseline.

---

## Scenario 1 — BaseModel arg registers as INPUT_OBJECT (User Story 1 / FR-001..003)

**File**: `tests/test_compose_introspection.py::TestInputTypeEdgeCases::test_input_payload_arg_registers_input_object_type`

```bash
uv run pytest tests/test_compose_introspection.py::TestInputTypeEdgeCases \
  -k payload_arg_registers -v
```

Expected outcome:
- An INPUT_OBJECT TypeInfo named `CreateTaskInput` exists in the registry.
- Its `input_fields` match the pydantic model's fields (`title`, `priority`, `note`).
- `priority.default_value == 5`; `note.default_value is None`; `title` has no default.
- See [contracts/registry-shape.md](contracts/registry-shape.md) for the exact struct.

Related: `test_input_field_default_value_preserved`, `test_optional_input_field_is_nullable`, `test_list_input_field_nullability`.

---

## Scenario 2 — Same model as return AND arg does not crash (User Story 2 / FR-004..005)

**File**: `tests/test_compose_introspection.py::TestInputTypeEdgeCases::test_dto_used_as_both_return_and_arg_arg_is_input_object`

```bash
uv run pytest tests/test_compose_introspection.py::TestInputTypeEdgeCases \
  -k both_return_and_arg -v
```

Expected outcome:
- `build_compose_schema(app)` does NOT raise `DuplicateTypeError`.
- Registry contains both `TaskDTO` (OBJECT) and `TaskDTOInput` (INPUT_OBJECT).
- `args[0].type_ref` walks to a leaf named `TaskDTOInput`, never `TaskDTO`.
- Nested input closure consistency: a field `inner: InnerInput` where `InnerInput` is also a return resolves to `InnerInputInput` everywhere.
- See [contracts/registry-shape.md](contracts/registry-shape.md#behavioral-rules-load-bearing-for-consumers) for the rename rules.

---

## Scenario 3 — Method SDL expands INPUT_OBJECT types (User Story 3 / FR-006..007)

**File**: `tests/test_compose_introspection.py::TestInputTypeEdgeCases::test_method_sdl_expands_input_object_referenced_by_args`

```bash
uv run pytest tests/test_compose_introspection.py::TestInputTypeEdgeCases \
  -k method_sdl_expands -v
```

Expected outcome — `render_method_sdl("TaskService", "create_task")` returns an SDL containing:
- `input CreateTaskInput { ... }` block (referenced by the arg, defined in the closure).
- All nested input types recursively expanded.
- No referenced type is left undefined.
- See [contracts/method-sdl.md](contracts/method-sdl.md) for the exact SDL.

---

## Scenario 4 — GraphiQL round-trips (cross-cutting / FR-008 / SC-002)

**File**: `tests/test_compose_introspection.py::TestGraphiQLCompatibility::test_canonical_graphiql_introspection_query_works`

```bash
uv run pytest tests/test_compose_introspection.py::TestGraphiQLCompatibility -v
```

Expected outcome:
- The canonical GraphiQL introspection query runs through `compose_introspect(app, query)` without error.
- The resulting JSON, fed to `graphql.build_client_schema(introspection_json)`, produces a valid schema with NO validation errors.

This is the spec-compliance gate — if it's green, the whole feature is spec-correct.

---

## Scenario 5 — Regression gate (FR-009 / SC-003)

```bash
uv run pytest tests/test_compose_schema.py tests/test_compose_introspect.py \
  tests/test_compose_executor.py tests/test_compose_mcp_server.py -q
```

Expected outcome: all pre-existing tests pass unchanged. Apps with zero BaseModel args produce byte-identical schemas to before the fix.

For an explicit byte-equivalence check, capture the registry dump of a no-arg app before and after the feature branch — the JSON dumps must match.

---

## Manual sanity probe (optional)

If you want to eyeball the output without running pytest:

```bash
uv run python -c "
from nexusx.use_case.compose_schema import build_compose_schema
from nexusx.use_case.compose_introspect import compose_introspect
import json

# Build a tiny demo app (see tests/conftest.py for the helper)
app = build_demo_app_with_input_arg()
schema = build_compose_schema(app)
print(schema.render_method_sdl('TaskService', 'create_task'))
print('---')
print(json.dumps(compose_introspect(app, '{ __type(name: \"CreateTaskInput\") { name kind inputFields { name defaultValue } } }'), indent=2))
"
```

Expected: SDL shows `input CreateTaskInput { ... }` and the introspection JSON shows `kind: INPUT_OBJECT` with `inputFields` populated.

---

## Done when

- [ ] Scenarios 1–4 pass (new tests in `tests/test_compose_introspection.py`).
- [ ] Scenario 5 passes (no regressions).
- [ ] Manual sanity probe produces the expected SDL + JSON shape from [contracts/](contracts/).

Then `/speckit-tasks` breaks the implementation work into actionable pieces.
