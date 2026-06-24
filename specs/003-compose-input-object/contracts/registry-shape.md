# Contract: `build_compose_schema` Registry Shape

**Surface**: `nexusx.use_case.compose_schema.build_compose_schema(app) -> ComposeSchema`
**Consumers**: `compose_introspect`, `render_method_sdl`, `compose_executor`, MCP server (`compose_mcp_server`).

## Before / After

The Python API signature is unchanged. What changes is the *content* of `ComposeSchema.registry: dict[str, TypeInfo]` when an app declares methods with BaseModel args.

## Inputs

```python
class TaskService(UseCaseService):
    @mutation
    async def create_task(self, payload: CreateTaskInput) -> TaskDTO: ...

class CreateTaskInput(BaseModel):
    title: str
    priority: int = 5
    note: str | None = None

class TaskDTO(BaseModel):
    id: int
    title: str
```

## Output (after fix)

```python
schema = build_compose_schema(app)
# schema.registry keys (order independent):
#   "Query"                       OBJECT  — root
#   "TaskServiceMutation"         OBJECT  — service entry
#   "TaskDTO"                     OBJECT  — from return type
#   "CreateTaskInput"             INPUT_OBJECT  ← NEW (was missing or OBJECT before)
#   + built-in scalars (String/Int/…) registered lazily
```

### `CreateTaskInput` TypeInfo (NEW shape — `input_fields` populated)

```
TypeInfo(
    name="CreateTaskInput",
    kind="INPUT_OBJECT",
    description=<CreateTaskInput.__doc__ or None>,
    fields=(),                       # OBJECT-only slot — empty for INPUT_OBJECT
    input_fields=(
        ArgumentInfo(name="title",   type_ref=non_null(Str), has_default=False, default_value=None),
        ArgumentInfo(name="priority", type_ref=non_null(Int), has_default=True,  default_value=5),
        ArgumentInfo(name="note",    type_ref=nullable(Str), has_default=True,  default_value=None),
    ),
    enum_values=(),
    python_class=CreateTaskInput,    # NEW — internal back-reference
)
```

### Method field on `TaskServiceMutation`

```
FieldInfo(
    name="create_task",
    type_ref=non_null(TypeRef(kind="OBJECT", name="TaskDTO")),
    args=(
        ArgumentInfo(
            name="payload",
            type_ref=non_null(TypeRef(kind="INPUT_OBJECT", name="CreateTaskInput")),  # ← was OBJECT before
            has_default=False,
        ),
    ),
)
```

## Behavioral rules (load-bearing for consumers)

| Rule | Detail |
|------|--------|
| Naming on conflict | Same BaseModel as both return and arg → arg-side entry renamed `{Name}Input` (e.g. `TaskDTO` as arg → `TaskDTOInput`). All `type_ref` leaves pointing at the arg version pick up the renamed name. |
| Distinct-class guard | Two distinct classes sharing `__name__` → `DuplicateTypeError` (unchanged). |
| Idempotency | Registering the same class twice (e.g. referenced by two args) produces one TypeInfo. |
| Closure consistency | Nested input fields referencing another input type resolve to that type's *single registered name* (renamed or not), via `_by_python_id`. |
| Frozen structs | `TypeInfo` / `FieldInfo` / `ArgumentInfo` remain `@dataclass(frozen=True, slots=True)`. Mutating the registry after `build_compose_schema` returns is unsupported. |
| No-arg regression | Apps that declare zero BaseModel args produce a registry byte-equivalent (same names, kinds, fields) to the pre-fix implementation. |
