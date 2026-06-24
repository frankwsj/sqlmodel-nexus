# Contract: `render_method_sdl` — INPUT_OBJECT Blocks

**Surface**: `nexusx.use_case.compose_schema.ComposeSchema.render_method_sdl(service_name, method_name) -> str | None`
**Consumers**: MCP `describe_compose_method` tool (4-layer progressive disclosure), docs generation, AI-agent SDL preview.

## Inputs

```python
class TaskService(UseCaseService):
    @mutation
    async def create_task(self, payload: CreateTaskInput) -> TaskDTO: ...

class CreateTaskInput(BaseModel):
    title: str
    priority: int = 5
    note: str | None = None
    tags: list[str] = []      # default_factory — not renderable as a literal
```

## Output (after fix)

`sdl = schema.render_method_sdl("TaskService", "create_task")`:

```graphql
# TaskService.create_task(payload: CreateTaskInput!): TaskDTO!

"""Query entry points for TaskService."""
type TaskServiceMutation {
  create_task(payload: CreateTaskInput!): TaskDTO!
}

type TaskDTO {
  id: Int!
  title: String!
}

input CreateTaskInput {
  title: String!
  priority: Int! = 5
  note: String
}
```

## Structural rules

| Rule | Detail |
|------|--------|
| Header comment | `# {Service}.{method}({args}): {return}` on line 1 — args rendered with `INPUT_OBJECT`-aware type refs. |
| Owning service block | Always emitted first; only the one method appears (filtered from the full service). |
| Closure includes args | Every type reachable from `method_field.type_ref` AND from each `arg.type_ref` appears in the closure, not just the return closure. |
| INPUT_OBJECT recursion | A nested input like `Outer { inner: Inner }` causes both `input Outer { ... }` and `input Inner { ... }` to appear. |
| Keyword | `input X { … }` for `kind == INPUT_OBJECT`; `type X { … }` for OBJECT; `enum X { … }` for ENUM; `scalar X` for SCALAR. Already implemented at `compose_schema.py:819`; activates once INPUT_OBJECT TypeInfos exist. |
| Default literal | `priority: Int! = 5` (the `= {literal}` suffix). `note: String` — no suffix (nullable, default null is implicit). `tags: [String!]!` — no suffix (mutable default, not representable — see `research.md` Decision 7). |
| Description placement | Block string `"""..."""` above the header line (NOT inside the braces — spec violation). Already implemented. |
| Field ordering | `sorted(reachable.items())` alphabetical by type name (existing behavior, unchanged). Within a type, fields appear in pydantic declaration order (existing behavior, unchanged). |

## Rename-on-conflict case (User Story 2)

```python
@mutation
async def upsert_task(self, patch: TaskDTO) -> TaskDTO: ...
```

SDL:

```graphql
# TaskService.upsert_task(patch: TaskDTOInput!): TaskDTO!

type TaskServiceMutation {
  upsert_task(patch: TaskDTOInput!): TaskDTO!
}

type TaskDTO {
  id: Int!
  title: String!
}

input TaskDTOInput {
  id: Int!
  title: String!
}
```

The arg leaf name is `TaskDTOInput`, never `TaskDTO`. The return-side `type TaskDTO { … }` and arg-side `input TaskDTOInput { … }` both appear; they do NOT collide (different GraphQL names).

## What `render_method_sdl` does NOT change

- Output for methods with no BaseModel args: byte-identical to pre-fix output.
- Output for methods whose args are all scalars / enums / lists-of-scalars: byte-identical to pre-fix output.
- `_render_sdl` (full schema, not method-scoped): unchanged structurally, but now includes `input X { … }` blocks for any INPUT_OBJECT in the registry.
