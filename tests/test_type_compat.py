"""Tests for type_compat.is_compatible_type — auto-load type checking."""

from __future__ import annotations

from pydantic import BaseModel
from sqlmodel import SQLModel

from nexusx.subset import DefineSubset
from nexusx.utils.type_compat import is_compatible_type


class TestIsCompatibleType:
    def test_same_type(self):
        """Same type should be compatible."""
        assert is_compatible_type(int, int) is True

    def test_direct_equality(self):
        """src is tgt should return True."""
        class Foo:
            pass
        assert is_compatible_type(Foo, Foo) is True

    def test_optional_unwrap(self):
        """Optional[Src] should unwrap and check Src vs tgt."""
        assert is_compatible_type(int | None, int) is True

    def test_non_optional_union_rejected(self):
        """Non-Optional Union should be rejected."""
        assert is_compatible_type(int | str, int) is False

    def test_list_compatible(self):
        """list[Src] should be compatible with list[Tgt] if Src is compatible."""
        assert is_compatible_type(list[int], list[int]) is True

    def test_list_incompatible(self):
        """list[Src] should be incompatible with list[Tgt] if Src is not compatible."""
        assert is_compatible_type(list[int], list[str]) is False

    def test_list_vs_non_list(self):
        """list[X] vs non-list should be incompatible."""
        assert is_compatible_type(list[int], int) is False

    def test_subset_chain(self):
        """DefineSubset of target should be compatible."""
        class Entity(SQLModel, table=False):
            id: int

        class DTO(DefineSubset):
            __subset__ = (Entity, ("id",))

        assert is_compatible_type(DTO, Entity) is True

    def test_unrelated_types(self):
        """Completely unrelated types should be incompatible."""
        assert is_compatible_type(str, int) is False

    def test_subclass_check(self):
        """Subclass should be compatible with parent."""
        class Parent:
            pass
        class Child(Parent):
            pass
        assert is_compatible_type(Child, Parent) is True

    def test_optional_src_list_compatible(self):
        """Optional[list[X]] should be compatible with list[X] after unwrap."""
        assert is_compatible_type(list[int] | None, list[int]) is True
