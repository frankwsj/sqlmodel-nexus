# Data Model: Compose Schema Metadata

**Feature**: 003-compose-input-object
**Scope**: The metadata structs used by `nexusx.use_case.compose_schema` — `TypeRef`, `TypeInfo`, `FieldInfo`, `ArgumentInfo`, `EnumValueInfo`. No business entities involved (see `spec.md` Phase 0 N/A rationale).

This feature extends the existing metadata model so that `INPUT_OBJECT` — already a literal in `LeafKind` and `TypeInfo.input_fields` (both currently unused) — is actually produced by the builder and rendered by the SDL / introspection layers.

---

## Existing structs (unchanged)

These already exist at `src/nexusx/use_case/compose_schema.py:55-140` and are NOT modified by this feature:

```python
TypeRef          # kind + (name | of_type)  — wrapper-aware reference to a type
EnumValueInfo    # name + description + deprecation_reason — single enum value
```

`TypeRef.kind` already includes `"INPUT_OBJECT"` in its `Literal` (line 50). The feature activates a previously-dormant leaf kind.

---

## Changed: `TypeInfo`

`src/nexusx/use_case/compose_schema.py:128-138`

```diff
 @dataclass(frozen=True, slots=True)
 class TypeInfo:
     name: str
     kind: LeafKind                                   # "INPUT_OBJECT" now reachable in practice
     description: str | None = None
     fields: tuple[FieldInfo, ...] = ()               # OBJECT only — unchanged
     enum_values: tuple[EnumValueInfo, ...] = ()      # ENUM only — unchanged
     input_fields: tuple[ArgumentInfo, ...] = ()      # INPUT_OBJECT only — WAS always empty, now populated
     specified_by_url: str | None = None
+    python_class: type | None = None                 # back-reference for rename-on-conflict matching
```

**Why `python_class`**: the rename-on-conflict check ("is *this* Python class already registered?") must match on identity, not on GraphQL name — because the input version may have already been renamed to `{Name}Input`. See `research.md` Decision 2.

**Default `None`**: SCALAR / ENUM registrations leave this unset. The field is internal bookkeeping; never serialized to introspection JSON or SDL.

**Frozen invariant preserved**: `python_class` is set once at construction time inside `_register_object` / `_register_input_object` and never mutated.

---

## Unchanged: `FieldInfo`

`src/nexusx/use_case/compose_schema.py:102-116` — unchanged. nexusx uses `ArgumentInfo` (not FieldInfo) for `TypeInfo.input_fields`, so input-field defaults already have a home on `ArgumentInfo.default_value`. (Upstream uses `FieldInfo` polymorphically for both OBJECT fields and input_fields; an early draft of this spec mirrored that, but the FieldInfo.default_value addition was dead code in nexusx and reverted during US1 implementation.)

---

## Unchanged: `ArgumentInfo`

`src/nexusx/use_case/compose_schema.py:83-99`

Already has everything needed: `name`, `type_ref`, `has_default`, `default_value`, `description`, `is_from_context`. The arg's `type_ref` may now point at an `INPUT_OBJECT` leaf, but the dataclass shape is unchanged.

---

## Activation matrix — what changes per leaf kind

| `TypeInfo.kind` | `fields` | `input_fields` | `enum_values` | `python_class` | SDL keyword | Rendered as |
|-----------------|----------|-----------------|---------------|-----------------|-------------|-------------|
| SCALAR          | empty    | empty           | empty         | None            | `scalar X`  | unchanged |
| OBJECT          | populated | empty          | empty         | set (if Pydantic)| `type X { … }` | unchanged |
| ENUM            | empty    | empty           | populated     | None            | `enum X { … }` | unchanged |
| **INPUT_OBJECT** | empty   | **populated (NEW)** | empty     | **set (NEW)**   | **`input X { … }` (NEW)** | **NEW** |

The INPUT_OBJECT row is what this feature activates. The other three rows are byte-identical to the pre-fix behavior — this is the regression gate (FR-009).

---

## Registry-level invariants (load-bearing)

The `{name: TypeInfo}` registry produced by `build_compose_schema(app)` must satisfy:

1. **Type-name uniqueness across kinds**: a name appears at most once, regardless of kind. Same Python class serving as both OBJECT (return) and INPUT_OBJECT (arg) → the input version is renamed `{Name}Input`. (Spec rule: a type name uniquely identifies a kind.)
2. **Distinct-class uniqueness**: two distinct Python classes that happen to share `__name__` still raise `DuplicateTypeError`. The rename-on-conflict only triggers when the SAME class (identity match via `python_class is cls`) appears in both phases.
3. **Idempotent registration**: calling `_register_input_object(cls)` twice produces one TypeInfo entry, not two. The second call returns the existing name.
4. **INPUT_OBJECT closure consistency**: if `OuterInput.inner: InnerInput` references a class that's also used as a return, every reference — `OuterInput.inner.type_ref`, any sibling arg referencing `InnerInput`, any nested input referencing it — resolves to the SAME renamed leaf (`InnerInputInput`). The `_by_python_id` map guarantees this because all references look up `id(cls)` and get the one registered name back.

---

## Two-phase build contract

`build_compose_schema(app)` must internally sequence:

```
Phase A.1: for each method, register all OBJECT types reachable from its return type.
Phase A.2: for each method, walk args and register all INPUT_OBJECT types reachable
           (renaming on conflict with Phase A.1 registrations).
Phase A.3: build method FieldInfo + ArgumentInfo with type_refs that reference
           the now-stable names from A.1/A.2.
```

Phase A.1 must complete before A.2 starts. Within A.2, `_register_input_object` recurses through input field types immediately, so nested INPUT_OBJECTs are registered in the same pass.

Today's single-pass `_build_service_fields` is restructured to collect method metadata first, then run the two registration phases, then assemble FieldInfo objects. The public signature of `build_compose_schema` and `ComposeSchema` is unchanged.
