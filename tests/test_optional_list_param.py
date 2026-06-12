"""Regression test: list[str] | None parameter should produce [String], not String.

Bug: _python_type_to_graphql() checks `origin is list` before checking Optional.
For `list[str] | None`, `get_origin()` returns UnionType, not list, so the list
check is skipped. Then Optional branch calls _python_type_to_graphql_inner() on
the unwrapped `list[str]`, which doesn't handle list types — falling back to String.

See: sdl_generator._python_type_to_graphql lines 20-48
"""
from typing import Optional

from sqlmodel import Field, SQLModel

from nexusx import mutation, query
from nexusx.sdl_generator import SDLGenerator, _python_type_to_graphql
from nexusx.type_converter import TypeConverter


# ── Entity with list[str] | None parameter ────────────────────────────


class ItemForListBug(SQLModel):
    """Test entity with optional list parameter."""

    id: int | None = Field(default=None, primary_key=True)
    name: str

    @mutation
    async def create_with_optional_tags(
        cls, name: str, tags: list[str] | None = None
    ) -> "ItemForListBug":
        """Create item with optional tag list."""
        return ItemForListBug(id=1, name=name)

    @mutation
    async def create_with_required_tags(
        cls, name: str, tags: list[str]
    ) -> "ItemForListBug":
        """Create item with required tag list."""
        return ItemForListBug(id=1, name=name)

    @mutation
    async def create_with_optional_typing(
        cls, name: str, tags: Optional[list[str]] = None
    ) -> "ItemForListBug":
        """Create item using Optional[list[str]] syntax."""
        return ItemForListBug(id=1, name=name)

    @query
    async def search_optional_ints(
        cls, ids: list[int] | None = None
    ) -> list["ItemForListBug"]:
        """Query with optional list[int]."""
        return []


# ── Tests ─────────────────────────────────────────────────────────────


class TestOptionalListParameterBug:
    """list[T] | None should serialize to [T!], not String."""

    def setup_method(self) -> None:
        self.converter = TypeConverter(set())

    # --- Direct type conversion ---

    def test_list_str_none_produces_list_string(self):
        """list[str] | None should convert to [String!], not String."""
        result = _python_type_to_graphql(list[str] | None, self.converter)
        assert result == "[String!]", f"Expected '[String!]' but got '{result}'"

    def test_optional_list_str_produces_list_string(self):
        """Optional[list[str]] should convert to [String!], not String."""
        result = _python_type_to_graphql(Optional[list[str]], self.converter)
        assert result == "[String!]", f"Expected '[String!]' but got '{result}'"

    def test_list_int_none_produces_list_int(self):
        """list[int] | None should convert to [Int!], not String."""
        result = _python_type_to_graphql(list[int] | None, self.converter)
        assert result == "[Int!]", f"Expected '[Int!]' but got '{result}'"

    def test_required_list_still_works(self):
        """list[str] (without None) should still produce [String!]!."""
        result = _python_type_to_graphql(list[str], self.converter)
        assert result == "[String!]!"

    # --- Full SDL generation ---

    def test_sdl_optional_list_param_is_list_type(self):
        """In generated SDL, list[str] | None param should appear as [String!], not String."""
        generator = SDLGenerator([ItemForListBug])
        sdl = generator.generate()

        # The required list version should work correctly
        assert "tags: [String!]!" in sdl, "Required list[str] should be [String!]!"

        # The optional list version — THIS IS THE BUG
        # Currently produces: tags: String
        # Should produce:     tags: [String!]
        assert "tags: [String!]" in sdl, (
            f"Optional list[str] | None should produce '[String!]', not 'String'.\n"
            f"SDL:\n{sdl}"
        )

    def test_sdl_optional_typing_list_param(self):
        """Optional[list[str]] (typing module) should also produce [String!]."""
        generator = SDLGenerator([ItemForListBug])
        sdl = generator.generate()

        # find the createWithOptionalTyping mutation
        # its `tags` param should be [String!], not String
        assert "tags: [String!]" in sdl, (
            f"Optional[list[str]] should produce '[String!]' in SDL.\n"
            f"SDL:\n{sdl}"
        )

    def test_sdl_optional_list_int_param(self):
        """list[int] | None param should produce [Int!], not String."""
        generator = SDLGenerator([ItemForListBug])
        sdl = generator.generate()

        assert "ids: [Int!]" in sdl, (
            f"list[int] | None should produce '[Int!]' in SDL.\n"
            f"SDL:\n{sdl}"
        )

    def test_list_of_optional_entity_produces_nullable_element_list(self):
        """list[Entity | None] should produce [Entity], not [String!]."""
        converter = TypeConverter({"ItemForListBug"})
        result = _python_type_to_graphql(
            list[ItemForListBug | None], converter, entity_names={"ItemForListBug"}
        )
        assert result == "[ItemForListBug]!", (
            f"Expected '[ItemForListBug]!' but got '{result}'"
        )

    def test_list_of_optional_scalar_produces_nullable_element_list(self):
        """list[str | None] should produce [String], not [String!]."""
        result = _python_type_to_graphql(list[str | None], self.converter)
        assert result == "[String]!", f"Expected '[String]!' but got '{result}'"
