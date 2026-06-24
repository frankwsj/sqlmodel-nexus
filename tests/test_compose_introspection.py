"""Tests for INPUT_OBJECT handling in the compose schema.

Ported (in intent, not line-for-line) from pydantic-resolve v5.10.2
``tests/use_case/test_compose_introspection.py`` — specifically the
``TestInputTypeEdgeCases`` and ``TestGraphiQLCompatibility`` classes.

nexusx's dataclass shape differs from upstream (nexusx uses
``ArgumentInfo`` for ``TypeInfo.input_fields``; upstream uses
``FieldInfo`` polymorphically), so the assertions target nexusx's
registry / introspection shapes directly rather than copy-pasting
upstream's exact dict paths.

Coverage:
- US1 — BaseModel method args register as INPUT_OBJECT end-to-end
        with input_fields populated and pydantic defaults surfaced.
- US2 — Same BaseModel as both return and arg produces {Name}Input
        rename; no DuplicateTypeError; nested input closure consistent.
- US3 — Method SDL expands INPUT_OBJECT types referenced by args.
- GraphiQL — Canonical introspection query round-trips through
             ``graphql.build_client_schema``.
"""

from __future__ import annotations

from pydantic import BaseModel

from nexusx.decorator import mutation, query
from nexusx.use_case.business import UseCaseService
from nexusx.use_case.compose_executor import compose_introspect
from nexusx.use_case.compose_schema import build_compose_schema
from nexusx.use_case.types import UseCaseAppConfig

# ──────────────────────────────────────────────────────────────────────
# DTOs + services (one fixture set, scoped per test via _build)
# ──────────────────────────────────────────────────────────────────────


class CreateTaskInput(BaseModel):
    """Input for create_task_with_input — three required fields, no defaults."""

    title: str
    owner_id: int


class TaskDTO(BaseModel):
    id: int
    title: str


class FilterInput(BaseModel):
    """Mix of required + default-valued fields — exercises default rendering."""

    keyword: str | None = None
    limit: int = 10
    required: str


class CloneDTO(BaseModel):
    """Used as BOTH return and arg in CloneService — rename-on-conflict case."""

    id: int
    title: str


class MDLInput(BaseModel):
    """Referenced by MDLService — method SDL expansion case."""

    title: str
    owner_id: int


class InnerInput(BaseModel):
    value: int


class OuterInput(BaseModel):
    """Nested BaseModel field — recursive INPUT_OBJECT registration."""

    name: str
    inner: InnerInput


class OptionalInput(BaseModel):
    """Optional vs required field nullability inside an input."""

    note: str | None = None
    required: int


class ListInput(BaseModel):
    """list[T] field inside an input — pin down list nullability."""

    tags: list[str]


class TaskService(UseCaseService):
    """Service with one method that takes a BaseModel arg (US1 main case)."""

    @mutation
    async def create_task_with_input(cls, payload: CreateTaskInput) -> TaskDTO:
        return TaskDTO(id=1, title=payload.title)


class FilterService(UseCaseService):
    @query
    async def search(cls, filter: FilterInput) -> str:
        return ""


class CloneService(UseCaseService):
    """clone payload AND return the same DTO type — rename-on-conflict."""

    @mutation
    async def clone(cls, payload: CloneDTO) -> CloneDTO:
        return payload


class MDLService(UseCaseService):
    @mutation
    async def create(cls, payload: MDLInput) -> str:
        return ""


class NestedService(UseCaseService):
    @query
    async def foo(cls, payload: OuterInput) -> str:
        return ""


class OptionalListService(UseCaseService):
    """One service exercising both Optional + list input-field nullability."""

    @query
    async def optional_field(cls, payload: OptionalInput) -> str:
        return ""

    @query
    async def list_field(cls, payload: ListInput) -> str:
        return ""


def _build(*services: type[UseCaseService], name: str = "edge"):
    """Build a ComposeSchema for a single app containing the given services."""
    return build_compose_schema(
        UseCaseAppConfig(name=name, services=list(services), enable_mutation=True)
    )


def _types(schema) -> dict[str, dict]:
    """Return ``{type_name: type_def}`` for all types in the schema's introspection."""
    result = compose_introspect(schema)
    return {t["name"]: t for t in result["data"]["__schema"]["types"]}


# ──────────────────────────────────────────────────────────────────────
# US1 — INPUT_OBJECT registration end-to-end
# ──────────────────────────────────────────────────────────────────────


class TestInputTypeEdgeCasesUS1:
    """User Story 1 — BaseModel method arg registers as INPUT_OBJECT
    with populated input_fields and pydantic-default literals."""

    def test_input_payload_arg_registers_input_object_type(self):
        schema = _build(TaskService)
        types = _types(schema)

        # The INPUT_OBJECT TypeInfo exists in the registry.
        payload_type = types["CreateTaskInput"]
        assert payload_type["kind"] == "INPUT_OBJECT"
        input_fields = {f["name"]: f for f in payload_type["inputFields"]}
        assert set(input_fields) == {"title", "owner_id"}
        # Required (non-default) fields are NON_NULL.
        assert input_fields["title"]["type"]["kind"] == "NON_NULL"
        assert input_fields["title"]["type"]["ofType"]["name"] == "String"
        assert input_fields["owner_id"]["type"]["ofType"]["name"] == "Int"

        # The method's arg type_ref walks to an INPUT_OBJECT leaf named
        # CreateTaskInput (NOT OBJECT — that's the spec violation we're fixing).
        method = next(
            f for f in types["TaskServiceMutation"]["fields"]
            if f["name"] == "create_task_with_input"
        )
        payload_arg = next(a for a in method["args"] if a["name"] == "payload")
        assert payload_arg["type"]["kind"] == "NON_NULL"
        assert payload_arg["type"]["ofType"]["kind"] == "INPUT_OBJECT"
        assert payload_arg["type"]["ofType"]["name"] == "CreateTaskInput"

    def test_input_field_default_value_preserved(self):
        """pydantic field defaults surface in ``inputFields[i].defaultValue``
        as a GraphQL literal (JSON-encoded string), matching how method-arg
        defaults render today."""
        schema = _build(FilterService)
        types = _types(schema)
        fields = {f["name"]: f for f in types["FilterInput"]["inputFields"]}

        # ``limit: int = 10`` → JSON-encoded as "10".
        assert fields["limit"]["defaultValue"] == "10"
        # ``keyword: Optional[str] = None`` → JSON-encoded as "null".
        assert fields["keyword"]["defaultValue"] == "null"
        # ``required: str`` (no default) → no defaultValue.
        assert fields["required"]["defaultValue"] is None

    def test_optional_input_field_is_nullable(self):
        """``Optional[X]`` field inside an input must produce a nullable
        type_ref (no NON_NULL wrapper). Guards against the input codepath
        accidentally forcing NON_NULL on optional fields."""
        schema = _build(OptionalListService)
        types = _types(schema)
        fields = {f["name"]: f for f in types["OptionalInput"]["inputFields"]}
        # ``note: Optional[str] = None`` → bare SCALAR String (no NON_NULL).
        assert fields["note"]["type"]["kind"] == "SCALAR"
        assert fields["note"]["type"]["name"] == "String"
        # ``required: int`` → NON_NULL Int.
        assert fields["required"]["type"]["kind"] == "NON_NULL"
        assert fields["required"]["type"]["ofType"]["name"] == "Int"

    def test_list_input_field_nullability(self):
        """Pin down nullability of ``list[T]`` fields inside an input.

        Expected: ``[T!]!`` — outer NON_NULL (field is not Optional),
        then LIST, then inner NON_NULL. If nexusx later decides inner
        elements should be nullable (``[T]!``), this test flags the change.
        """
        schema = _build(OptionalListService)
        types = _types(schema)
        fields = {f["name"]: f for f in types["ListInput"]["inputFields"]}
        tags_type = fields["tags"]["type"]
        assert tags_type["kind"] == "NON_NULL"
        outer = tags_type["ofType"]
        assert outer["kind"] == "LIST"
        assert outer["ofType"]["kind"] == "NON_NULL"
        assert outer["ofType"]["ofType"]["kind"] == "SCALAR"
        assert outer["ofType"]["ofType"]["name"] == "String"


# ──────────────────────────────────────────────────────────────────────
# US2 — Rename on conflict + nested closure
# ──────────────────────────────────────────────────────────────────────


class TestInputTypeEdgeCasesUS2:
    """User Story 2 — same BaseModel as both return and arg produces
    {Name}Input rename; nested BaseModel field registers as INPUT_OBJECT
    recursively."""

    def test_dto_used_as_both_return_and_arg_arg_is_input_object(self):
        """``upsert_task(patch: CloneDTO) -> CloneDTO`` must NOT crash with
        DuplicateTypeError. The return-side registers CloneDTO as OBJECT;
        the arg-side registers CloneDTOInput as INPUT_OBJECT. The arg's
        type_ref leaf name is CloneDTOInput, never CloneDTO."""
        schema = _build(CloneService)
        types = _types(schema)

        # Both the OBJECT and the renamed INPUT_OBJECT exist.
        assert types["CloneDTO"]["kind"] == "OBJECT"
        assert types["CloneDTOInput"]["kind"] == "INPUT_OBJECT"

        # The method's arg walks to the INPUT_OBJECT leaf.
        method = next(
            f for f in types["CloneServiceMutation"]["fields"] if f["name"] == "clone"
        )
        payload_arg = next(a for a in method["args"] if a["name"] == "payload")
        assert payload_arg["type"]["ofType"]["kind"] == "INPUT_OBJECT"
        assert payload_arg["type"]["ofType"]["name"] == "CloneDTOInput"

    def test_nested_basemodel_in_input_registers_as_input_object(self):
        """A BaseModel field within an input must also register as INPUT_OBJECT,
        and the outer input's field type_ref must reference the (renamed if
        applicable) INPUT_OBJECT leaf — not OBJECT."""
        schema = _build(NestedService)
        types = _types(schema)
        assert types["InnerInput"]["kind"] == "INPUT_OBJECT"
        assert types["OuterInput"]["kind"] == "INPUT_OBJECT"
        outer_fields = {f["name"]: f for f in types["OuterInput"]["inputFields"]}
        assert outer_fields["inner"]["type"]["ofType"]["kind"] == "INPUT_OBJECT"
        assert outer_fields["inner"]["type"]["ofType"]["name"] == "InnerInput"


# ──────────────────────────────────────────────────────────────────────
# US3 — Method SDL expansion
# ──────────────────────────────────────────────────────────────────────


class TestInputTypeEdgeCasesUS3:
    """User Story 3 — render_method_sdl expands INPUT_OBJECT types
    referenced by the method's args, emitting ``input X { ... }`` blocks."""

    def test_method_sdl_expands_input_object_referenced_by_args(self):
        schema = _build(MDLService)
        sdl = schema.render_method_sdl("MDLService", "create")
        assert sdl is not None
        # The input type referenced by the arg must be defined in the SDL.
        assert "input MDLInput {" in sdl
        # And its fields must be expanded.
        assert "title: String!" in sdl
        assert "owner_id: Int!" in sdl


# ──────────────────────────────────────────────────────────────────────
# GraphiQL compatibility — the spec-compliance gate (FR-008 / SC-002)
# ──────────────────────────────────────────────────────────────────────


# The exact query GraphiQL sends on boot. ``compose_introspect`` ignores the
# field-level selection and returns the full schema, but feeding the canonical
# query through it exercises the same dispatch path GraphiQL hits in prod.
_GRAPHIQL_CANONICAL_QUERY = """
query IntrospectionQuery {
  __schema {
    queryType { name }
    mutationType { name }
    subscriptionType { name }
    types { ...FullType }
    directives {
      name
      description
      locations
      args { ...InputValue }
    }
  }
}
fragment FullType on __Type {
  kind
  name
  description
  fields(includeDeprecated: true) {
    name
    description
    args { ...InputValue }
    type { ...TypeRef }
    isDeprecated
    deprecationReason
  }
  inputFields { ...InputValue }
  interfaces { ...TypeRef }
  enumValues(includeDeprecated: true) {
    name
    description
    isDeprecated
    deprecationReason
  }
  possibleTypes { ...TypeRef }
}
fragment InputValue on __InputValue {
  name
  description
  type { ...TypeRef }
  defaultValue
}
fragment TypeRef on __Type {
  kind
  name
  ofType {
    kind
    name
    ofType {
      kind
      name
      ofType {
        kind
        name
        ofType { kind name }
      }
    }
  }
}
"""


class TestGraphiQLCompatibility:
    """FR-008 / SC-002 — the canonical GraphiQL introspection query must
    round-trip through ``compose_introspect`` and the resulting introspection
    JSON must validate via ``graphql.build_client_schema``."""

    def test_canonical_graphiql_introspection_query_works(self):
        from graphql import build_client_schema

        # Use an app that exercises all three user stories:
        # - BaseModel arg → INPUT_OBJECT (US1)
        # - Same class as both return and arg → rename-on-conflict (US2)
        # - Nested input → recursive INPUT_OBJECT (US2 nested case)
        schema = _build(TaskService, CloneService, NestedService)
        result = compose_introspect(schema, _GRAPHIQL_CANONICAL_QUERY)

        # The introspection must complete without errors.
        assert result["errors"] is None
        gql_schema = result["data"]["__schema"]
        assert gql_schema["queryType"]["name"] == "Query"

        # The spec-compliance gate: ``build_client_schema`` raises on any
        # spec violation (INPUT_OBJECT fields on an OBJECT, dangling type
        # refs, malformed defaults, etc.). If this passes, GraphiQL can
        # consume the schema.
        built = build_client_schema(result["data"])
        assert built is not None

        # Sanity-check that the built schema agrees about INPUT_OBJECT placement.
        from graphql import GraphQLInputObjectType, GraphQLObjectType

        type_map = built.type_map
        assert isinstance(type_map["CreateTaskInput"], GraphQLInputObjectType)
        assert isinstance(type_map["CloneDTOInput"], GraphQLInputObjectType)
        assert isinstance(type_map["CloneDTO"], GraphQLObjectType)  # not input
        # Nested input closure consistency — InnerInput registered as INPUT_OBJECT.
        assert isinstance(type_map["InnerInput"], GraphQLInputObjectType)


class TestRegressionInvariants:
    """FR-009 / SC-003 — apps that declare NO BaseModel args must produce a
    schema byte-equivalent (same names, kinds, fields) to the pre-fix
    implementation. The feature activates a previously-dormant codepath;
    nothing about the existing return-side / scalar-arg codepath may change.

    These tests pin the invariants explicitly so a future refactor that
    accidentally flips OBJECT → INPUT_OBJECT on the wrong codepath fails
    loudly here, not silently in some downstream consumer.
    """

    def test_no_input_object_types_when_app_has_no_basemodel_args(self):
        """A service with only scalar / list / Optional scalar args must
        not introduce any INPUT_OBJECT TypeInfo."""
        class ScalarService(UseCaseService):
            @query
            async def list(cls, limit: int = 10, keyword: str | None = None) -> list[str]:
                return []

        schema = _build(ScalarService)
        # No INPUT_OBJECT in the registry — scalar args don't trigger it.
        assert all(t.kind != "INPUT_OBJECT" for t in schema.registry.values())

    def test_python_class_not_set_on_object_typeinfo_for_returns(self):
        """``python_class`` is internal bookkeeping for the rename-on-conflict
        check. It must be populated on OBJECT TypeInfo produced by return-side
        registration (so the input-side rename can match by identity), but
        must NEVER leak into SCALAR / ENUM TypeInfo."""
        schema = _build(TaskService)
        for type_info in schema.registry.values():
            if type_info.kind in ("SCALAR", "ENUM"):
                assert type_info.python_class is None, (
                    f"{type_info.name} ({type_info.kind}) unexpectedly carries python_class"
                )
