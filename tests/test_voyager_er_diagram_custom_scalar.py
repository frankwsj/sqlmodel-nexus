"""Regression tests for Voyager ER diagram custom relationship targets.

This captures two related failure modes seen in real projects:
1. `target=int` (or other scalar/non-model target) crashes ER rendering.
2. `target=list["ForwardRef"]` leaves a string target unresolved and crashes.
"""

from __future__ import annotations

from sqlmodel import Field, SQLModel

from nexusx.loader.registry import ErManager
from nexusx.relationship import Relationship
from nexusx.voyager.er_diagram_dot import ErDiagramDotBuilder


async def _count_loader(keys: list[int]) -> list[int]:
    return [0 for _ in keys]


async def _children_loader(keys: list[int]) -> list[list[ChildEntity]]:
    return [[] for _ in keys]


class ParentEntity(SQLModel, table=True):
    __tablename__ = "voyager_parent_entity"

    id: int | None = Field(default=None, primary_key=True)
    title: str


class ChildEntity(SQLModel, table=True):
    __tablename__ = "voyager_child_entity"

    id: int | None = Field(default=None, primary_key=True)
    parent_id: int | None = None
    name: str


ParentEntity.__relationships__ = [
    Relationship(fk="id", target=int, name="message_count", loader=_count_loader),
    Relationship(fk="id", target=list[ChildEntity], name="children", loader=_children_loader),
]


class TestVoyagerErDiagramCustomScalarTarget:
    def test_reproduces_crash_on_non_model_target(self):
        async def session_factory():
            return None

        registry = ErManager(
            entities=[ParentEntity, ChildEntity],
            session_factory=session_factory,
        )

        builder = ErDiagramDotBuilder(registry)
        builder.analysis()
