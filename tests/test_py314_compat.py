"""Test: DefineSubset extra fields work on Python 3.14+ (PEP 649/749).

On Python 3.14+, __annotations__ is None in class body namespace and
annotations are lazily stored in __annotate_func__. The nexusx subset
module's _extract_extra_fields reads namespace['__annotations__'], which
returns None. This test verifies that the compat patch correctly extracts
annotations from __annotate_func__ and that DefineSubset extra fields
(relationship fields, derived fields) are properly recognized.

Run with: pytest tests/test_py314_compat.py
"""
import sys

import pytest
from sqlmodel import Field, SQLModel

from nexusx import DefineSubset, SubsetConfig

# ── Simple SQLModel entities for testing ──────────────────────────────


class _Item(SQLModel, table=True):
    __tablename__ = "py314_item"
    id: int | None = Field(default=None, primary_key=True)
    name: str


class _Tag(SQLModel, table=True):
    __tablename__ = "py314_tag"
    id: int | None = Field(default=None, primary_key=True)
    name: str


class _ItemTag(SQLModel, table=True):
    __tablename__ = "py314_item_tag"
    id: int | None = Field(default=None, primary_key=True)
    item_id: int = Field(foreign_key="py314_item.id")
    tag_id: int = Field(foreign_key="py314_tag.id")


# ── Test cases ────────────────────────────────────────────────────────


@pytest.mark.skipif(sys.version_info < (3, 14), reason="PEP 649 specific to Python 3.14+")
class TestPy314AnnotationsCompat:
    """Verify DefineSubset extra fields on Python 3.14+."""

    def test_extra_field_scalar(self):
        """Extra field with scalar type is recognized."""

        class TagSummary(DefineSubset):
            __subset__ = SubsetConfig(kls=_Tag, fields=["id", "name"])

        assert "id" in TagSummary.model_fields
        assert "name" in TagSummary.model_fields

    def test_extra_field_relationship_single(self):
        """Extra field with DTO type (MANYTOONE) is recognized."""

        class TagBrief(DefineSubset):
            __subset__ = SubsetConfig(kls=_Tag, fields=["id", "name"])

        class ItemTagDTO(DefineSubset):
            __subset__ = SubsetConfig(
                kls=_ItemTag, fields=["id", "tag_id"], excluded_fields=["tag_id"]
            )
            tag: TagBrief | None = None

        assert "tag" in ItemTagDTO.model_fields
        assert "tag_id" in ItemTagDTO.model_fields

    def test_extra_field_relationship_list(self):
        """Extra field with list[DTO] type (ONETOMANY) is recognized."""

        class TagBrief(DefineSubset):
            __subset__ = SubsetConfig(kls=_Tag, fields=["id", "name"])

        class ItemTagDTO(DefineSubset):
            __subset__ = SubsetConfig(
                kls=_ItemTag, fields=["id", "tag_id"], excluded_fields=["tag_id"]
            )
            tag: TagBrief | None = None

        class ItemDTO(DefineSubset):
            __subset__ = SubsetConfig(kls=_Item, fields=["id", "name"])
            item_tags: list[ItemTagDTO] = []

        assert "item_tags" in ItemDTO.model_fields

    def test_extra_field_derived(self):
        """Extra field for derived computation (post_*) is recognized."""

        class ItemDTO(DefineSubset):
            __subset__ = SubsetConfig(kls=_Item, fields=["id", "name"])
            tag_count: int = 0

            def post_tag_count(self):
                return self.tag_count

        assert "tag_count" in ItemDTO.model_fields

    def test_model_validate_roundtrip(self):
        """DTO with extra fields can validate from ORM entity."""

        class TagBrief(DefineSubset):
            __subset__ = SubsetConfig(kls=_Tag, fields=["id", "name"])

        class ItemTagDTO(DefineSubset):
            __subset__ = SubsetConfig(
                kls=_ItemTag, fields=["id", "tag_id"], excluded_fields=["tag_id"]
            )
            tag: TagBrief | None = None

        class ItemDTO(DefineSubset):
            __subset__ = SubsetConfig(kls=_Item, fields=["id", "name"])
            item_tags: list[ItemTagDTO] = []

        item = _Item(id=1, name="Test Item")
        dto = ItemDTO.model_validate(item)
        assert dto.id == 1
        assert dto.name == "Test Item"
        assert dto.item_tags == []

    def test_excluded_field_hidden_in_dump(self):
        """FK field with excluded_fields is hidden from model_dump."""

        class TagBrief(DefineSubset):
            __subset__ = SubsetConfig(kls=_Tag, fields=["id", "name"])

        class ItemTagDTO(DefineSubset):
            __subset__ = SubsetConfig(
                kls=_ItemTag, fields=["id", "tag_id"], excluded_fields=["tag_id"]
            )
            tag: TagBrief | None = None

        link = _ItemTag(id=1, item_id=10, tag_id=20)
        dto = ItemTagDTO.model_validate(link)
        dumped = dto.model_dump()
        assert "tag_id" not in dumped
        assert "id" in dumped
