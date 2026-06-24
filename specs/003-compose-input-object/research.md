# Research: Compose Schema INPUT_OBJECT Handling

**Feature**: 003-compose-input-object
**Date**: 2026-06-24
**Reference upstream**: pydantic-resolve `184886d` (v5.10.2) — `pydantic_resolve/use_case/compose_schema.py`, `pydantic_resolve/graphql/schema/type_registry.py`, `tests/use_case/test_compose_introspection.py` (307 new lines).

This research maps each upstream fix onto nexusx's existing architecture and locks the design decisions before `data-model.md` / `contracts/` are written.

---

## Architectural delta — upstream vs nexusx

The two codebases look superficially similar (both walk `UseCaseService` classes, both produce a `{name: TypeInfo}` registry, both render SDL + introspection JSON). But one structural difference changes **where** the fix lives:

| Concern | Upstream (pydantic-resolve) | nexusx |
|---------|------------------------------|--------|
| TypeInfo / FieldInfo store the Python annotation | yes — `FieldInfo.python_type: Any` | **no** — `FieldInfo.type_ref: TypeRef` is fully materialized at build time |
| Type-ref construction | `_build_type_ref(python_type, registry, …)` called **at render time** | `_map_leaf` → `TypeRef` called **at build time**, stored on FieldInfo |
| Rename-on-conflict (`{Name}Input`) | Render-time: `_override_input_name` walks the type-ref chain after the fact | **Must be build-time**: the stored `type_ref` already names the leaf |
| TypeInfo knows its source Python class | yes — `TypeInfo.python_class` | **no** — TypeInfo has only `name` / `kind` / fields |

**Consequence**: nexusx cannot copy upstream's `_override_input_name` trick. The rename has to happen inside the mapper at registration time, and TypeInfo needs a way to remember which Python class it was built from so the rename-on-conflict check can match.

Everything else (two-phase build, INPUT_OBJECT recursion in closure walk, `input` SDL keyword, default-literal rendering) ports close to verbatim.

---

## Decision 1 — `is_input` parameter plumbing

**Decision**: Add `is_input: bool = False` to `ComposeTypeMapper._map_leaf` and propagate it through `_map` → containers (`_map_list`, `_map_optional`) → leaf registration. Public `map_python_type(py_type)` keeps its current signature (default `is_input=False`); add `map_python_type_as_input(py_type)` as the input-side entrypoint so call sites read loudly.

**Rationale**:
- nexusx's `map_python_type` is called from both `_get_return_type` / `_build_service_fields` (return side) and `_build_method_arguments` (arg side). A bare new param on `map_python_type` would be easy to forget at one of those sites; a separate `map_python_type_as_input` makes wrong-site calls visible at grep time.
- Pushing `is_input` all the way down to `_map_leaf` (rather than only into `_register_*`) lets `Optional[CreateTaskInput]` and `list[CreateTaskInput]` keep their wrapper nullability semantics unchanged while still producing an INPUT_OBJECT leaf.
- Scalars and enums ignore `is_input` (they're kind-agnostic in GraphQL), so the param is a no-op for them — no behavioral risk to non-BaseModel args.

**Alternatives rejected**:
- *Separate `ComposeInputTypeMapper` subclass*: more code, duplicates `_map`/`_map_list`/`_map_optional` for a 3-line behavioral difference. Rejected.
- *Post-hoc mutation of the registry after build*: violates nexusx's frozen-dataclass invariant (`TypeInfo` is `@dataclass(frozen=True, slots=True)`). Rejected.

---

## Decision 2 — TypeInfo gains a back-reference to its source class

**Decision**: Add `python_class: type | None = None` to `TypeInfo`. Populated by `_register_object` / `_register_input_object` via `id(cls)` lookup against the existing `_by_python_id` map (already used for de-dup on the OBJECT side).

**Rationale**:
- The rename-on-conflict check needs to answer "is *this* Python class already registered as INPUT_OBJECT?" — name-based matching breaks when the input version has already been renamed to `{Name}Input`. Upstream uses `python_class is cls` for exactly this reason (see `_override_input_name`).
- `None` default keeps existing SCALAR / ENUM registrations unchanged (they have no meaningful source class).
- The field is not exposed in introspection JSON or SDL — it's internal bookkeeping. Documented under `data-model.md`.

**Alternatives rejected**:
- *External `dict[id, TypeInfo]` only*: already exists (`_by_python_id`), but it can only answer "what's registered for this id?" — not "what name did it get?" in the rename case without a follow-up lookup. Carrying `python_class` on TypeInfo keeps the check a single pass.

---

## Decision 3 — `{Name}Input` rename happens at registration time

**Decision**: New `_register_input_object(cls)` method on `ComposeTypeMapper`. Logic:

1. If `id(cls)` already maps to an INPUT_OBJECT TypeInfo → return that TypeInfo's name (idempotent).
2. Compute the candidate name = `cls.__name__`.
3. If a TypeInfo with that name already exists in `_registry` AND its `kind == "OBJECT"` AND its `python_class is cls` → rename candidate to `f"{cls.__name__}Input"`. (Same class used as both return and arg.)
4. If a TypeInfo with that name already exists AND its `python_class is not cls` → raise `DuplicateTypeError` (two distinct classes sharing a name — unchanged behavior).
5. Else register `TypeInfo(name=candidate, kind="INPUT_OBJECT", python_class=cls, input_fields=...)`.

**Rationale**:
- This is the build-time equivalent of upstream's render-time `_override_input_name`. Because nexusx's `FieldInfo.type_ref` stores the leaf name at build time, the name written into the TypeRef IS the final name — no render-time walk needed.
- Step 3's `python_class is cls` guard means two distinct classes that happen to share a Python `__name__` (different modules) still raise `DuplicateTypeError` — preserves the existing guard (spec edge case 4 in `spec.md`).
- `_by_python_id` is keyed by `id(cls)`. When the input version is registered (possibly under a renamed GraphQL name), the SAME `id(cls)` maps to the renamed TypeInfo. Subsequent references from sibling input fields / nested input models look up `_by_python_id[id(cls)]` and get the renamed name back for free — recursion is consistent automatically.

**Alternatives rejected**:
- *Defer rename to render time like upstream*: would require storing `python_type` on FieldInfo and rewriting nexusx's whole mapper return contract. ~200 lines of churn. Rejected.
- *Don't rename, raise a clear error instead*: violates FR-005 (must not crash) and user story 2 acceptance.

---

## Decision 4 — Two-phase build in `build_compose_schema`

**Decision**: Restructure `build_compose_schema` so the per-method walk happens in two phases:

- **Phase A (returns)**: for each method, register the return type's reachable Pydantic models as OBJECT (today's behavior). Build the method's `FieldInfo` with its `type_ref` and its `ArgumentInfo` objects (with their final `type_ref`s — see Decision 5 for why arg type_refs are already correct by this point).
- **Phase B (args)**: for each method, walk each arg's reachable types with `is_input=True` and register INPUT_OBJECTs (with rename-on-conflict).

Today's `_build_service_fields` does per-method (return + args) registration in one pass; the change is to collect all method metadata in phase A, register all returns, then register all args, then assemble TypeInfo objects.

**Phase ordering is load-bearing**: phase A must complete before phase B, so phase B sees existing OBJECT entries and can rename on conflict. If we interleaved per-method (register method-1 returns, then method-1 args, then method-2 returns, …), a method-2 return would register an OBJECT AFTER method-1's arg already grabbed the bare name — producing an inconsistent registry.

**Why arg type_refs can be built in phase A but their INPUT_OBJECT registrations deferred to phase B**: because `map_python_type_as_input` consults `_by_python_id` (Decision 3, step 1). The arg's type_ref resolves to the right leaf name regardless of whether the INPUT_OBJECT TypeInfo has been *fully populated with input_fields* yet — as long as the TypeInfo stub exists in the registry with the right name. So the sequence is:

1. Phase A.1: register all return OBJECTs.
2. Phase A.2: register all arg INPUT_OBJECT stubs (with `python_class` set, `input_fields` still empty) — this fixes the names.
3. Phase A.3: build method `FieldInfo` + `ArgumentInfo` with `type_ref`s that reference the now-stable names.
4. Phase B: populate `input_fields` on each INPUT_OBJECT (recursively, since nested fields may reference other INPUT_OBJECTs).

In practice this collapses to: register returns, then register args (which both stubs and populates, since `_register_input_object` recurses through field types immediately — same pattern as `_register_object` does today for OBJECT fields).

---

## Decision 5 — `_collect_closure` recursion + arg seeding

**Decision**: Extend `_collect_closure` (used by `_render_method_sdl`) in two ways:

1. **Seed from args too**: caller passes both the method's return `type_ref` AND each arg's `type_ref`. Implemented as a small `for ref in refs:` loop at the top of `render_method_sdl`, or by changing `_collect_closure`'s signature to take a list.
2. **Recurse through INPUT_OBJECT `input_fields`**: today the comment says "SCALAR / ENUM / INPUT_OBJECT: leaf, no further recursion needed". After the fix, INPUT_OBJECT must recurse through its `input_fields[*].type_ref` — same as OBJECT recurses through `fields[*].type_ref`.

**Rationale**:
- Without arg seeding, the method SDL references `CreateTaskInput` in the arg list but never defines it — user story 3's bug.
- Without INPUT_OBJECT recursion, a nested input like `Outer { inner: Inner }` references `Inner` but never defines it.
- Both are pure additions to today's behavior (no existing OBJECT closure walk changes).

---

## Decision 6 — SDL keyword + `input_fields` source

**Decision**: In `_emit_type_sdl`, the existing `keyword = "type" if t.kind == "OBJECT" else "input"` already produces the right keyword for INPUT_OBJECT (the ENUM and SCALAR branches return early above it). What needs to change is the field source: for `kind == INPUT_OBJECT`, iterate `t.input_fields` (a `tuple[ArgumentInfo, ...]`), not `t.fields`.

Also: input fields have no `args` (they're leaf values, not method-like fields), so the `arg_str` block in `_emit_type_sdl` is skipped for INPUT_OBJECT fields. Easiest implementation is a tiny branch:

```python
field_source = t.input_fields if t.kind == "INPUT_OBJECT" else t.fields
for f in field_source:
    # for INPUT_OBJECT fields, f.args is always empty so arg_str stays ""
    ...
```

**Rationale**:
- nexusx already has both `fields` and `input_fields` slots on TypeInfo (lines 135 + 137 of compose_schema.py). Keeping them separate is less invasive than merging them upstream-style.
- `ArgumentInfo` already has `has_default` + `default_value`, so the `= {literal}` clause on input fields falls out for free from the existing SDL logic.

---

## Decision 7 — Default-value literal rendering

**Decision**: For each pydantic field on an INPUT_OBJECT, set `ArgumentInfo.default_value` to the JSON-encoded literal of the pydantic default (i.e. `json.dumps(field.default)` when `field.default is not PydanticUndefined`). The existing `_sdl_literal` already serializes JSON values into GraphQL literals, and `_json_default` already handles them in introspection output — so no new serializer is needed, just plumbing.

For mutable defaults (`default_factory=...`): pydantic exposes them via `field.default_factory`, not `field.default` (which is `PydanticUndefined` in that case). nexusx will treat `default_factory is not None` as "no static literal available" and surface it the same way as `PydanticUndefined` — i.e. no `= ...` clause, no `defaultValue` key. (Matches upstream's behavior; called out as edge case 3 in `spec.md`.)

**Rationale**:
- nexusx already uses `param.default` for method-arg defaults (line 478 of `_build_method_arguments`). The pattern is to JSON-encode it for SDL via `_sdl_literal` and pass it through to introspection as-is. Reusing the same codepath for input-field defaults keeps the two surfaces consistent.
- pydantic's `PydanticUndefined` sentinel is the only new import — explicit guard against accidentally rendering the sentinel as `null`.

---

## Decision 8 — Test layout

**Decision**: Add a new `tests/test_compose_introspection.py` parallel to upstream's `tests/use_case/test_compose_introspection.py`. Include the 7 `TestInputTypeEdgeCases` tests verbatim-in-intent, plus a `TestGraphiQLCompatibility` test that round-trips through `graphql.build_client_schema` (SC-002 in `spec.md`).

**Rationale**:
- nexusx already has `tests/test_compose_introspect.py` (introspection execution) and `tests/test_compose_schema.py` (registry shape). A new `test_compose_introspection.py` matches upstream's name and groups the input-type edge cases together.
- The `build_client_schema` round-trip is the single highest-value test — it's the spec-compliance gate (FR-008). If GraphiQL can't consume the introspection, nothing else matters.

**Alternatives rejected**:
- *Extend `test_compose_schema.py`*: that file already covers registry-shape concerns; mixing in introspection-output concerns muddles it. Separate file, parallel to upstream.

---

## What is explicitly NOT in scope

- Changing `TypeInfo` / `FieldInfo` from `frozen=True` to mutable. The fix works within the frozen constraint.
- Storing `python_type` on FieldInfo (upstream style). nexusx's `type_ref`-baked approach is preserved.
- Replacing `map_python_type` with a polymorphic `map(py_type, *, is_input=False)`. The asymmetric pair `map_python_type` / `map_python_type_as_input` is preferred for grep-visibility (Decision 1).
- Touching the executor (`compose_executor.py`). Input-object handling at query-execution time is already correct — the args come in as dicts and pydantic validates them. Only the *schema* was wrong.
- Backfilling `defaultValue` rendering for method-arg (non-input) defaults. Already works (line 478 + `_sdl_literal`); no change needed.

---

## Open questions resolved before plan sign-off

None. All decisions above are taken from the upstream reference implementation (verbatim where nexusx's structure allows, adapted where it doesn't) and are internally consistent with `spec.md`'s FR-001..FR-009.
