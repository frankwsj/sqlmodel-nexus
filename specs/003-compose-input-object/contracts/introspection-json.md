# Contract: `compose_introspect` JSON — INPUT_OBJECT Rendering

**Surface**: `nexusx.use_case.compose_introspect(app, query: str) -> dict`
**Spec source**: GraphQL October 2021 introspection. **Validation gate**: `graphql.build_client_schema(introspection_json)` MUST succeed (FR-008 / SC-002).

## Inputs

Same app as in `registry-shape.md` (TaskService.create_task with CreateTaskInput arg). Query:

```graphql
{
  __schema {
    types {
      name
      kind
      fields { name args { name type { kind name ofType { kind name } } } }
      inputFields { name type { kind name ofType { kind name } } defaultValue }
    }
  }
}
```

## Output — INPUT_OBJECT entry in `__schema.types`

Before the fix: either no entry with `name="CreateTaskInput"`, or an entry with `kind="INPUT_OBJECT"` but `inputFields: null`. After:

```json
{
  "name": "CreateTaskInput",
  "kind": "INPUT_OBJECT",
  "description": null,
  "fields": null,
  "inputFields": [
    { "name": "title",   "type": {"kind": "NON_NULL", "name": null, "ofType": {"kind": "SCALAR", "name": "String", "ofType": null}}, "defaultValue": null },
    { "name": "priority","type": {"kind": "NON_NULL", "name": null, "ofType": {"kind": "SCALAR", "name": "Int",    "ofType": null}}, "defaultValue": 5 },
    { "name": "note",    "type": {"kind": "SCALAR",   "name": "String", "ofType": null}, "defaultValue": null }
  ],
  "interfaces": null,
  "enumValues": null,
  "possibleTypes": null
}
```

Notes:
- `fields` is `null` (INPUT_OBJECT has no fields per spec — only `inputFields`).
- `interfaces` is `null` (INPUT_OBJECT implements none — per spec).
- `defaultValue` is the JSON-native Python object (`5`, `null`, `"hi"`, `true`), NOT a GraphQL-literal string. The MCP transport will encode this through `json.dumps`; `graphql-core` accepts both per spec, but the canonical GraphiQL introspection uses JSON-native values and that's what nexusx emits.

## Output — method arg `type` ref

The `create_task` field's `args[0]` (the `payload` arg):

```json
{
  "name": "payload",
  "type": {
    "kind": "NON_NULL",
    "name": null,
    "ofType": {"kind": "INPUT_OBJECT", "name": "CreateTaskInput", "ofType": null}
  }
}
```

The leaf `kind` is `INPUT_OBJECT` (was `OBJECT` before — spec violation). After rename-on-conflict (User Story 2), the leaf `name` is the renamed `TaskDTOInput`, not the original `TaskDTO`.

## Output — `__type(name: "...")` query

`compose_introspect(app, "{ __type(name: \"CreateTaskInput\") { name kind inputFields { name } } }")` returns a single-type view with the same shape as the corresponding `__schema.types` entry (no array wrapper).

## GraphiQL compatibility gate

The full canonical GraphiQL introspection query (the one GraphiQL sends on connect) MUST round-trip without errors and produce a `build_client_schema`-valid result. This is the single most important acceptance test (upstream `TestGraphiQLCompatibility.test_canonical_graphiql_introspection_query_works`, ported into `tests/test_compose_introspection.py`).

## What the introspection output does NOT change

- SCALAR / OBJECT / ENUM entries: byte-identical to pre-fix output.
- `__schema.directives`: the 5 standard directives (`@skip`, `@include`, `@deprecated`, `@specifiedBy`, `@oneOf`) — unchanged.
- `queryType` / `mutationType` / `subscriptionType` root pointers — unchanged.
